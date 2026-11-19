"""Paper-only watch: how the S2/S4 rules would have done on stocks that are watched but never recommended."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from tradeagent.config import Config
from tradeagent.setups.library import LIBRARY, STOCKS
from tradeagent.setups.simulate import simulate

WATCH_SETUPS = ("S2", "S4")  # stock setups; ETFs were not added to the watch


@dataclass(frozen=True)
class GroupStats:
    setup_id: str
    group: str            # "watched" or "traded"
    trades: int
    win_rate: float | None
    avg_r: float | None
    avg_ret: float | None


def _closed_trades(bars: dict[str, pd.DataFrame], symbols, setup, since: pd.Timestamp, cost: float) -> pd.DataFrame:
    rows = []
    for sym in symbols:
        df = bars.get(sym)
        if df is None or len(df) < 260:
            continue
        for t in simulate(df, setup, sym, cost, 252):
            if t.entry_date >= since and t.reason != "end":     # only trades that actually closed
                rows.append({"symbol": sym, "entry": t.entry_date, "r": t.r, "ret": t.ret})
    return pd.DataFrame(rows)


def compare(bars: dict[str, pd.DataFrame], config: Config, since: str) -> list[GroupStats]:
    """Watched vs traded stocks, per setup, for trades entered on or after ``since``."""
    cost = config.backtest.round_trip_cost
    out = []
    for setup in (s for s in LIBRARY if s.id in WATCH_SETUPS):
        for group, symbols in (("watched", config.paper_watch.stocks), ("traded", STOCKS)):
            df = _closed_trades(bars, symbols, setup, pd.Timestamp(since), cost)
            if df.empty:
                out.append(GroupStats(setup.id, group, 0, None, None, None))
            else:
                out.append(GroupStats(setup.id, group, len(df), float((df["ret"] > 0).mean()),
                                      float(df["r"].mean()), float(df["ret"].mean())))
    return out


def review_due(bars: dict[str, pd.DataFrame], config: Config) -> dict[str, int]:
    """Closed paper trades per setup since the watch started; a setup is due for review at review_after_trades."""
    counts = {g.setup_id: g.trades for g in compare(bars, config, config.paper_watch.watch_start) if g.group == "watched"}
    return {sid: n for sid, n in counts.items() if n >= config.paper_watch.review_after_trades}


def to_markdown(stats: list[GroupStats], since: str, config: Config) -> str:
    lines = [f"## Watched on paper (never recommended), trades entered since {since}", "",
             "| Setup | Group | Closed trades | Winners | Avg R | Avg per trade |", "|---|---|---|---|---|---|"]
    for g in stats:
        lines.append(f"| {g.setup_id} | {g.group} | {g.trades} | "
                     f"{'–' if g.win_rate is None else f'{g.win_rate:.0%}'} | "
                     f"{'–' if g.avg_r is None else f'{g.avg_r:+.2f}'} | "
                     f"{'–' if g.avg_ret is None else f'{g.avg_ret:+.2%}'} |")
    lines += ["", f"Review rule: once the watched stocks have {config.paper_watch.review_after_trades} closed paper trades "
              f"for a setup since {config.paper_watch.watch_start}, the weekly report asks whether to add them."]
    return "\n".join(lines) + "\n"
