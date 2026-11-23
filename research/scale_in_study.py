"""Scaling in on confirmation, steps 1-2 (rules fixed in research/ideas_ledger.json, idea 2026-11-23-3, before running).

Every S2/S3/S4 trade (current exits, 0.1% round trip) is replayed with a starter of fraction f and one add of
a = (1 - f) / (1 + k) at the next open after a close >= entry + k x R. The stop never moves, so the most a trade can
lose is 1R of a full-size position. Profit is in R of a full-size position. Step 1 picks the best variant on
2015-2023; step 2 needs it to beat all-at-once by >= +0.05R per trade on 2024-2025.

Run:  uv run python research/scale_in_study.py
"""

import json
from itertools import product
from pathlib import Path

import numpy as np
import pandas as pd

from tradeagent import prices
from tradeagent.config import load_config
from tradeagent.setups.library import LIBRARY, ETFS, CORE_ETFS, TRADED_STOCKS
from tradeagent.setups.simulate import simulate_swing

OUT = Path(__file__).resolve().parent / "results"
F = (1 / 3, 1 / 2, 2 / 3)
K = (0.5, 1.0, 1.5)
PERIODS = {"design": ("2015-01-01", "2023-12-31"), "check": ("2024-01-01", "2025-12-31"), "final": ("2026-01-01", "2026-11-20")}


def scaled(trade, df, f, k, cost):
    """Profit in full-size R for one trade under (f, k); the add fills at the next open after a confirming close."""
    o, c = df["open"].to_numpy(float), df["close"].to_numpy(float)
    e, x = df.index.get_loc(trade.entry_date), df.index.get_loc(trade.exit_date)
    r0 = trade.entry - trade.stop
    base = (trade.exit - trade.entry - cost * trade.entry) / r0
    assert abs(base - trade.r) < 1e-9                                    # all-at-once reproduces the backtest
    a = (1 - f) / (1 + k)
    add_px = None
    for d in range(e, x):
        if c[d] >= trade.entry + k * r0:
            nxt = d + 1
            exits_at_open = nxt == x and (trade.reason == "signal" or trade.exit == o[nxt])
            if not exits_at_open and o[nxt] > trade.stop:
                add_px = o[nxt]
            break
    part = (trade.exit - add_px - cost * add_px) / r0 if add_px is not None else 0.0
    return f * base + (a * part if add_px is not None else 0.0), add_px is not None


def main():
    cfg = load_config()
    cost = cfg.backtest.round_trip_cost
    syms = sorted(set(TRADED_STOCKS) | set(ETFS) | set(CORE_ETFS) | {"BIL", "^VIX"})
    bars, missing = prices.daily_bars(syms, "2014-01-01", "2026-11-20")
    assert not missing, missing
    rows = []
    for s in LIBRARY:
        if s.id not in ("S2", "S3", "S4"):
            continue
        for sym in s.universe:
            df = bars.get(sym)
            if df is None:
                continue
            for t in simulate_swing(df, s, sym, cost):
                if t.reason == "end" or t.entry_date < pd.Timestamp("2015-01-01"):
                    continue
                row = {"setup": s.id, "sym": sym, "entry_date": t.entry_date, "all_at_once": t.r}
                for f, k in product(F, K):
                    v, added = scaled(t, df, f, k, cost)
                    row[f"f{f:.2f}_k{k}"] = v
                    row[f"f{f:.2f}_k{k}_added"] = added
                rows.append(row)
    df = pd.DataFrame(rows)
    df["period"] = pd.cut(df.entry_date, [pd.Timestamp(PERIODS[p][0]) for p in PERIODS] + [pd.Timestamp("2026-12-31")],
                          labels=list(PERIODS), right=False)
    variants = [f"f{f:.2f}_k{k}" for f, k in product(F, K)]
    table = []
    for p in PERIODS:
        g = df[df.period == p]
        r = {"period": p, "trades": len(g), "all_at_once": g.all_at_once.mean()}
        r.update({v: g[v].mean() for v in variants})
        table.append(r)
    t = pd.DataFrame(table).set_index("period")
    best = t.loc["design", variants].astype(float).idxmax()
    chk = df[df.period == "check"]
    diff = chk[best] - chk.all_at_once
    se = diff.std() / np.sqrt(len(diff))
    passed = diff.mean() >= 0.05
    res = {"best_on_design": best, "design_best": float(t.at["design", best]), "design_all_at_once": float(t.at["design", "all_at_once"]),
           "check_best": float(t.at["check", best]), "check_all_at_once": float(t.at["check", "all_at_once"]),
           "check_gain": float(diff.mean()), "check_gain_90": [float(diff.mean() - 1.645 * se), float(diff.mean() + 1.645 * se)],
           "check_trades": int(len(chk)), "add_rate_design": float(df[df.period == "design"][best + "_added"].mean()),
           "step2_passed": bool(passed),
           "final_best": float(t.at["final", best]), "final_all_at_once": float(t.at["final", "all_at_once"])}
    OUT.mkdir(exist_ok=True)
    t.round(4).to_csv(OUT / "scale_in_steps12.csv")
    by_setup = df[df.period == "design"].groupby("setup")[["all_at_once", best]].mean().round(3)
    (OUT / "scale_in_steps12.json").write_text(json.dumps(res, indent=1))
    print(t.round(3).T.to_string())
    print("\nby setup on design:\n", by_setup.to_string())
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
