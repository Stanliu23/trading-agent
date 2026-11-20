"""Weekly re-score of the macro stress conditions (runs in the Saturday job, or `tradeagent macro-rescore`).

1. Re-simulate every S2/S3/S4 signal with the current exits (2015 to now).
2. Score each (setup, condition) with the fixed rules on rolling periods (design = 2015 to 2 years ago,
   check = the last 2 years).
3. Anything that would switch ON must also pass the 36-start account check (a failed check is reused for 4 weeks,
   since it takes a while to run); switching OFF needs no check.
4. Store every score and return the changes in plain English.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Callable, Optional

import pandas as pd

from tradeagent import account, macro_trust, prices
from tradeagent.config import Config
from tradeagent.papertrade import simulate_with_goal_rules
from tradeagent.setups.library import CORE_ETFS, ETFS, LIBRARY, STOCKS
from tradeagent.setups.simulate import simulate_swing


def past_trades(bars: dict[str, pd.DataFrame], config: Config) -> pd.DataFrame:
    rows = []
    for s in LIBRARY:
        if s.kind != "swing" or s.id == "S1":
            continue
        for sym in s.universe:
            df = bars.get(sym)
            if df is None:
                continue
            for t in simulate_swing(df, s, sym, config.backtest.round_trip_cost):
                i = df.index.get_loc(t.entry_date)
                if i > 0:
                    rows.append({"setup_id": s.id, "signal_day": df.index[i - 1], "r": t.r})
    return pd.DataFrame(rows)


def account_check(bars, config: Config, stats, earnings, mult: dict[str, pd.Series], today: date) -> tuple[bool, str]:
    """36 starts, 24 months, $300 + $250/month: the gate must win in >= 60% of starts, with a positive median and a
    median worst drop no more than 1 point deeper."""
    starts = [d for d in pd.date_range("2016-01-01", pd.Timestamp(today) - pd.DateOffset(months=25), freq="3MS")][-36:]
    diffs, drops = [], []
    for st in starts:
        end = (st + pd.DateOffset(months=24)).date().isoformat()
        res = []
        for mm in (None, mult):
            sim = simulate_with_goal_rules(bars, config, stats, st.date().isoformat(), end, 300, 250, earnings, macro_mult=mm)
            d = sim.daily
            dep = sum(a for _, a, _ in sim.deposits)
            dp = pd.Series({x: a for x, a, _ in sim.deposits[1:]}, dtype=float).reindex(d.index, fill_value=0)
            idx = (1 + ((d.value - dp) / d.value.shift(1) - 1).iloc[1:]).cumprod()
            res.append(((d.value.iloc[-1] - dep) / dep, float((idx / idx.cummax() - 1).min())))
        diffs.append((res[1][0] - res[0][0]) * 100)
        drops.append((res[1][1] - res[0][1]) * 100)
    s, dd = pd.Series(diffs), pd.Series(drops)
    ok = (s > 1e-9).mean() >= 0.6 and s.median() > 0 and dd.median() >= -1
    return ok, f"better in {(s > 1e-9).mean():.0%} of {len(s)} starts, median {s.median():+.2f} pts, drop {dd.median():+.2f} pts"


def rescore(config: Config, conn, now: Optional[datetime] = None,
            check: Optional[Callable[..., tuple[bool, str]]] = None) -> list[str]:
    now = now or datetime.now()
    today = now.date()
    bars, _ = prices.daily_bars(sorted(set(STOCKS) | set(ETFS) | set(CORE_ETFS) | {"BIL", *macro_trust.STRESS_SYMBOLS}),
                                "2013-01-01", today.isoformat())
    cond = macro_trust.conditions(bars)
    scores = macro_trust.score(past_trades({k: v.loc["2014-01-01":] for k, v in bars.items()}, config), cond, today)
    before = macro_trust.active(conn)
    need = [s for s in scores if s.passes and before.get((s.setup_id, s.condition)) != s.action]
    ok, notes = {}, []
    if need:
        import json
        from tradeagent.config import PROJECT_ROOT
        stats = {d["setup_id"]: d for d in json.loads((PROJECT_ROOT / "data" / "setup_stats.json").read_text())}
        earnings = account.earnings_dates(list(STOCKS), max_age_days=30)
        check = check or account_check
        from tradeagent import db
        for s in need:
            key = f"macro_check:{s.setup_id}:{s.condition}:{s.action}"
            last = db.get_meta(conn, key)            # "YYYY-MM-DD|0|why": a failed check is reused for 4 weeks
            if last and last.split("|")[1] == "0" and (today - date.fromisoformat(last[:10])).days < 28:
                ok[(s.setup_id, s.condition)] = False
                continue
            passed, why = check(bars, config, stats, earnings, macro_trust.multipliers({(s.setup_id, s.condition): s.action}, cond), today)
            ok[(s.setup_id, s.condition)] = passed
            conn.execute("INSERT INTO meta(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                         (key, f"{today.isoformat()}|{int(passed)}|{why}"))
            conn.commit()
            notes.append(f"Account check for {s.condition} on {s.setup_id}: {why}.")
    return macro_trust.record(conn, scores, ok, now) + notes
