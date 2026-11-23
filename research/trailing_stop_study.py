"""S2 trailing stop (rules fixed in research/ideas_ledger.json, idea 2026-11-23-2, before running).

S2 keeps its entry, 2xATR first stop and 20-session limit; the 4xATR target is removed; trail = max(first stop, highest
close since entry - 3 x ATR(14) at the signal close), from the next session. Step 1: on 2024-2025 entries at least
+0.05R per trade better than current S2 exits (R against the first stop; two separate trade lists). Step 2: 36 starts,
today's rules with S2 trailing vs today's rules: better in >= 60%, median gain > 0, median worst drop no more than
1 point deeper. 2026 reported. Step 2 runs only if step 1 passes.

Run:  uv run python research/trailing_stop_study.py
"""

import dataclasses
import json
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import big_dip_study as B  # noqa: E402  (same account harness and data)

OUT = B.OUT
PERIODS = {"design": ("2015-01-01", "2023-12-31"), "check": ("2024-01-01", "2025-12-31"), "final": ("2026-01-01", "2026-11-20")}


def s2_trail():
    from tradeagent.setups.library import get
    return dataclasses.replace(get("S2"), target_atr=None, trail_atr=3.0)


def _init():
    B._init({})
    lib = B._G["libs"]["TODAY"]
    B._G["libs"]["TRAIL"] = tuple(s2_trail() if s.id == "S2" else s for s in lib)


def one(job):
    variant, start, end = job
    pt = B._G["pt"]
    pt.LIBRARY = B._G["libs"][variant]
    sim = pt.simulate_with_goal_rules(B._G["bars"], B._G["cfg"], B._G["stats"], start, end, 300, 250, B._G["earn"])
    d = sim.daily
    dep = sum(a for _, a, _ in sim.deposits)
    dp = pd.Series({x: a for x, a, _ in sim.deposits[1:]}, dtype=float).reindex(d.index, fill_value=0)
    idx = (1 + ((d.value - dp) / d.value.shift(1) - 1).iloc[1:]).cumprod()
    s2 = [t for t in sim.trades if t.setup_id == "S2"]
    return {"variant": variant, "start": start, "gain": (d.value.iloc[-1] - dep) / dep * 100,
            "worst": float((idx / idx.cummax() - 1).min()) * 100, "s2_trades": len(s2), "s2_pnl": sum(t.pnl for t in s2)}


def main():
    from tradeagent.config import load_config
    from tradeagent.setups.library import get
    from tradeagent.setups.simulate import simulate_swing
    cfg = load_config()
    bars = B.load_bars()
    rows = []
    for name, s in (("current", get("S2")), ("trail", s2_trail())):
        for sym in s.universe:
            for t in simulate_swing(bars[sym], s, sym, cfg.backtest.round_trip_cost):
                if t.reason != "end" and t.entry_date >= pd.Timestamp("2015-01-01"):
                    rows.append({"variant": name, "entry_date": t.entry_date, "r": t.r, "reason": t.reason,
                                 "hold": t.hold_days})
    df = pd.DataFrame(rows)
    res = {"per_trade": {}}
    for p, (a, b) in PERIODS.items():
        g = df[(df.entry_date >= a) & (df.entry_date <= b)]
        res["per_trade"][p] = {v: {"trades": int(len(x)), "mean_r": round(float(x.r.mean()), 4),
                                   "win_rate": round(float((x.r > 0).mean()), 3), "avg_hold": round(float(x.hold.mean()), 1),
                                   "exits": x.reason.value_counts().to_dict()}
                               for v, x in g.groupby("variant")}
    chk = res["per_trade"]["check"]
    gain = chk["trail"]["mean_r"] - chk["current"]["mean_r"]
    res["step1"] = {"check_gain_r": round(gain, 4), "passed": gain >= 0.05}
    print(json.dumps(res, indent=1, default=str))
    if res["step1"]["passed"]:
        jobs = [(v, x, (pd.Timestamp(x) + pd.DateOffset(months=24)).date().isoformat()) for x in B.STARTS for v in ("TODAY", "TRAIL")]
        jobs += [(v, "2026-01-02", "2026-11-20") for v in ("TODAY", "TRAIL")]
        with ProcessPoolExecutor(12, initializer=_init) as ex:
            out = pd.DataFrame(list(ex.map(one, jobs)))
        out.to_csv(OUT / "trailing_stop_accounts.csv", index=False)
        a = out[out.start != "2026-01-02"].pivot(index="start", columns="variant", values=["gain", "worst"])
        diff, dd = a["gain"]["TRAIL"] - a["gain"]["TODAY"], a["worst"]["TRAIL"] - a["worst"]["TODAY"]
        ok = (diff > 1e-9).mean() >= 0.6 and diff.median() > 0 and dd.median() >= -1
        f = out[out.start == "2026-01-02"].set_index("variant")
        res["step2"] = {"better_share": float((diff > 1e-9).mean()), "median_gain_pts": float(diff.median()),
                        "median_drop_pts": float(dd.median()), "passed": bool(ok),
                        "gain_2026_pts": float(f.at["TRAIL", "gain"] - f.at["TODAY", "gain"])}
        res["result"] = "PASSED" if ok else "FAILED step 2"
        print("STEP 2:", res["step2"])
    else:
        res["result"] = "FAILED step 1"
    print("RESULT:", res["result"])
    (OUT / "trailing_stop_study.json").write_text(json.dumps(res, indent=1, default=str))


if __name__ == "__main__":
    main()
