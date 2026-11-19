"""`tradeagent replay`: replay recent months with a hypothetical account and count every alert.

Writes docs/REPLAY.md and data/replay/*.csv.
"""

from __future__ import annotations

import json
import time
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd

from tradeagent import market, prices
from tradeagent.config import PROJECT_ROOT, Config
from tradeagent.papertrade import SimResult, simulate_portfolio
from tradeagent.setups.library import CORE_ETFS, ETFS, LIBRARY, STOCKS


def _stats(root: Path) -> dict[str, dict]:
    data = json.loads((root / "data" / "setup_stats.json").read_text())
    return {d["setup_id"]: d for d in data}


def _watchlist_alerts(bars: dict[str, pd.DataFrame], start, config: Config) -> pd.DataFrame:
    """If every watchlist symbol were held: daily count of 2σ / 3σ moves (close-to-close and intraday touch)."""
    t = config.triggers
    rows = []
    for sym, df in bars.items():
        r = df["close"].pct_change()
        sigma = r.rolling(t.sigma_lookback_days).std().shift(1)
        prev = df["close"].shift(1)
        intra = pd.concat([(df["high"] / prev - 1).abs(), (df["low"] / prev - 1).abs()], axis=1).max(axis=1)
        z_c, z_i = (r.abs() / sigma).loc[start:], (intra / sigma).loc[start:]
        rows.append({"symbol": sym, "days": len(z_c),
                     "close_2s": int(((z_c >= t.move_sigma) & (z_c < t.urgent_move_sigma)).sum()),
                     "close_3s": int((z_c >= t.urgent_move_sigma).sum()),
                     "touch_2s": int(((z_i >= t.move_sigma) & (z_i < t.urgent_move_sigma)).sum()),
                     "touch_3s": int((z_i >= t.urgent_move_sigma).sum())})
    return pd.DataFrame(rows).set_index("symbol")


def _headline_volume(symbols: list[str], days: int = 7) -> pd.Series:
    cutoff = datetime.now().astimezone() - timedelta(days=days)
    out = {}
    for s in symbols:
        try:
            items = market.headlines(s)
        except Exception:
            out[s] = None
            continue
        out[s] = sum(1 for it in items if it["published"] and datetime.fromisoformat(it["published"]) >= cutoff)
        time.sleep(0.3)
    return pd.Series(out, dtype="float")


def run(config: Config, months: int = 6, starting_cash: float = 300, monthly_deposit: float = 250,
        root: Path = PROJECT_ROOT, with_news: bool = True) -> Path:
    today = date.today()
    start = (pd.Timestamp(today) - pd.DateOffset(months=months)).date()
    fetch_start = (pd.Timestamp(start) - pd.DateOffset(days=420)).date().isoformat()
    symbols = sorted(set(STOCKS) | set(ETFS) | set(CORE_ETFS))
    bars, missing = prices.daily_bars(symbols, fetch_start, today.isoformat())
    stats = _stats(root)

    earnings = {}
    for s in STOCKS:
        if s in bars:
            got = market.past_earnings(s, limit=12)
            if got:
                earnings[s] = got
            time.sleep(0.2)

    sim = simulate_portfolio(bars, config, stats, start.isoformat(), today.isoformat(),
                             starting_cash, monthly_deposit, earnings)
    watch = _watchlist_alerts(bars, pd.Timestamp(start), config)
    news = _headline_volume(symbols) if with_news else pd.Series(dtype="float")

    out_dir = root / "data" / "replay"
    out_dir.mkdir(parents=True, exist_ok=True)
    sim.daily.to_csv(out_dir / "daily.csv")
    pd.DataFrame([t.__dict__ for t in sim.trades]).to_csv(out_dir / "trades.csv", index=False)
    md = to_markdown(sim, watch, news, config, start, today, starting_cash, monthly_deposit, missing,
                     sorted(set(STOCKS) - set(earnings)), bars["SPY"]["close"])
    path = root / "docs" / "REPLAY.md"
    path.write_text(md, encoding="utf-8")
    return path


def _usd(x):
    return f"${x:,.2f}"


def to_markdown(sim: SimResult, watch, news, config, start, end, starting_cash, monthly_deposit, missing,
                no_earnings, sim_spy: pd.Series) -> str:
    d = sim.daily
    weeks = max(1, len(d) / 5)
    deposited = starting_cash + sum(a for _, a, _ in sim.deposits[1:])
    final = d["value"].iloc[-1]
    peak = d["value"].cummax()
    max_dd = float((d["value"] / peak - 1).min())
    trades = pd.DataFrame([t.__dict__ for t in sim.trades])
    idle = (d["cash_lt"] + d["cash_st"]) / d["value"]
    dep = pd.Series({day: amt for day, amt, _ in sim.deposits[1:]}, dtype=float).reindex(d.index, fill_value=0.0)
    twr_daily = ((d["value"] - dep) / d["value"].shift(1) - 1).iloc[1:]
    twr_index = (1 + twr_daily).cumprod()
    twr = float(twr_index.iloc[-1] - 1)
    twr_dd = float((twr_index / twr_index.cummax() - 1).min())
    spy = sim_spy.loc[d.index[0]:d.index[-1]]
    spy_ret = float(spy.iloc[-1] / spy.iloc[0] - 1)
    switch_day = d.index[d["profile"] == "moderate"].min() if (d["profile"] == "moderate").any() else None
    lines = [
        "# 6-month replay with a hypothetical account",
        "",
        f"Replay {start} to {end}: {len(d)} trading sessions. Starting cash {_usd(starting_cash)}, then "
        f"{_usd(monthly_deposit)} on the first session of each month. Every recommendation is assumed taken at "
        "the next open. Rules: `config.yaml` as approved. No real money.",
        "",
        "## The account",
        "",
        f"- Deposited {_usd(deposited)}; ended at **{_usd(final)}** "
        f"({_usd(final - deposited)}, {final / deposited - 1:+.1%} on money put in).",
        f"- **Time-weighted return** (deposits removed): {twr:+.1%}, vs SPY {spy_ret:+.1%} over the same sessions.",
        f"- Largest drop from a peak, time-weighted: {twr_dd:.1%}. (Raw account value: {max_dd:.1%}, softened by deposits.)",
        f"- Switched from aggressive to moderate on {switch_day.date() if switch_day is not None else 'never'}.",
        "- Goal (short-term must beat holding VTI/QQQ/SCHD over 3 months): "
        + ("; ".join(sim.notes) if sim.notes else "never fell behind at a weekly check."),
        f"- Profile at the end: {d['profile'].iloc[-1]}. Drawdown pause active on {int(d['paused'].sum())} sessions.",
        f"- Cash sitting idle: {idle.mean():.0%} of the account on average; {idle.iloc[-1]:.0%} at the end.",
        f"- Positions open at the end: {len(sim.open_positions)}; average open {d['positions'].mean():.1f}.",
        f"- Long-term share at the end: {(d['lt_value'].iloc[-1] + d['cash_lt'].iloc[-1]) / final:.0%}.",
        "",
    ]
    if not trades.empty:
        st = trades[trades["bucket"] == "short_term"]
        lines += ["## Short-term trades", "",
                  f"- {len(st)} closed trades, {(st['pnl'] > 0).mean():.0%} winners, total P&L {_usd(st['pnl'].sum())}.",
                  f"- Average position {_usd(st['dollars_in'].mean())}; smallest {_usd(st['dollars_in'].min())}; "
                  f"{int((st['dollars_in'] < 20).sum())} positions under $20.",
                  f"- Exits: " + ", ".join(f"{k} {v}" for k, v in st["reason"].value_counts().items()) + ".",
                  "", "| Setup | Trades | Win rate | P&L |", "|---|---|---|---|"]
        for sid, g in st.groupby("setup_id"):
            lines.append(f"| {sid} | {len(g)} | {(g['pnl'] > 0).mean():.0%} | {_usd(g['pnl'].sum())} |")
        lines.append("")
    lines += ["## Open positions at the end", "", "| Symbol | Setup | Bucket | Entry | Since |", "|---|---|---|---|---|"]
    for p in sim.open_positions:
        lines.append(f"| {p.symbol} | {p.setup_id} | {p.bucket.replace('_', '-')} | {_usd(p.entry)} × {p.qty:.4f} | {p.entry_day.date()} |")
    lines += ["", "## Signals not taken", "",
              f"{sim.signals_seen} setup signals fired on the watchlist; reasons some were not taken:", ""]
    for k, v in sim.blocked.most_common():
        lines.append(f"- {k}: {v}")
    lines += ["", "## Alerts this account would have produced", "", "| Alert | Count | Per week |", "|---|---|---|"]
    for k, v in sorted(sim.alerts.items()):
        lines.append(f"| {k} | {v} | {v / weeks:.1f} |")
    lines += ["", "## Watchlist alert rates (if every symbol were held)", "",
              f"{len(watch)} symbols over {int(watch['days'].median())} sessions.", "",
              "| Measure | Total | Per symbol per month |", "|---|---|---|"]
    months = max(1, len(d) / 21)
    for col, label in (("close_2s", "2σ–3σ close-to-close move"), ("close_3s", "≥3σ close-to-close move"),
                       ("touch_2s", "2σ–3σ intraday touch"), ("touch_3s", "≥3σ intraday touch")):
        tot = int(watch[col].sum())
        lines.append(f"| {label} | {tot} | {tot / len(watch) / months:.2f} |")
    if len(news):
        lines += ["", "## Yahoo headline volume (last 7 days, live)", "",
                  f"- Median {news.median():.0f} headlines per symbol; max {news.max():.0f} ({news.idxmax()}). "
                  f"Fetch failed for {int(news.isna().sum())} symbols."]
    if missing or no_earnings:
        lines += ["", "## Data gaps", ""]
        if missing:
            lines.append(f"- No price data: {', '.join(missing)}")
        if no_earnings:
            lines.append(f"- No earnings dates from Yahoo (entries blocked): {', '.join(no_earnings)}")
    return "\n".join(lines) + "\n"
