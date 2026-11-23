"""Backtest reference numbers for the learning questions Q3 and Q8 (docs/LEARNING.md), computed once from
2015-2025 prices with the current setup rules. Writes research/results/live_reference.json.

Q3: signals per calendar month per setup (every (symbol, day) with the setup's signal on, across its universe).
Q8: the average and spread of the setup's per-trade R (current exits, 0.1% round-trip cost).

Run:  uv run python research/learning_reference.py
"""

import json
from pathlib import Path

import pandas as pd

from tradeagent import prices
from tradeagent.config import load_config
from tradeagent.setups.library import LIBRARY, ETFS, CORE_ETFS, TRADED_STOCKS
from tradeagent.setups.simulate import simulate

OUT = Path(__file__).resolve().parent / "results" / "live_reference.json"
SETUPS = ("S2", "S3", "S4")


def main():
    cfg = load_config()
    syms = sorted(set(TRADED_STOCKS) | set(ETFS) | set(CORE_ETFS) | {"BIL", "^VIX"})
    bars, missing = prices.daily_bars(syms, "2014-01-01", "2026-11-20")
    assert not missing, missing
    out = {"made": "2026-11-23", "window": ["2015-01-01", "2025-12-31"], "setups": {}}
    for s in LIBRARY:
        if s.id not in SETUPS:
            continue
        counts, rs = pd.Series(dtype=float), []
        for sym in s.universe:
            df = bars.get(sym)
            if df is None:
                continue
            sig = s.signal(df).fillna(False).astype(bool).loc["2015-01-01":"2025-12-31"]
            counts = counts.add(sig.groupby(sig.index.to_period("M")).sum().astype(float), fill_value=0)
            rs += [t.r for t in simulate(df.loc[:"2025-12-31"], s, sym, cfg.backtest.round_trip_cost, 252)
                   if t.r is not None and t.entry_date >= pd.Timestamp("2015-01-01") and t.reason != "end"]
        months = pd.period_range("2015-01", "2025-12", freq="M")
        counts = counts.reindex(months, fill_value=0)
        r = pd.Series(rs, dtype=float)
        out["setups"][s.id] = {"monthly_signals": [int(x) for x in counts.to_numpy()],
                               "r_mean": round(float(r.mean()), 4), "r_sd": round(float(r.std()), 4), "r_n": int(len(r))}
        print(s.id, "signals/month median", counts.median(), "| R mean", round(r.mean(), 3), "sd", round(r.std(), 3), "n", len(r))
    OUT.write_text(json.dumps(out, indent=1))
    print("wrote", OUT)


if __name__ == "__main__":
    main()
