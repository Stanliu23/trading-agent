"""Big-dip D2 (rules fixed in research/ideas_ledger.json, idea 2026-11-23-6, before running): D1's signal; stop
2.5xATR; sell at the next open after the first close >= entry x 1.03; 20-session limit; at most 1 open; left out of the
goal check. Same steps and harness as research/big_dip_study.py.

Run:  uv run python research/big_dip_d2_study.py
"""

import dataclasses
import json
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import big_dip_study as B  # noqa: E402

OUT = B.OUT


def d2_setup():
    return dataclasses.replace(B.d1_setup(), id="D2", name="Big-dip rebound, quick profit",
                               rule="A stock's first close 30% or more below its highest close of the last 60 sessions. "
                                    "Sell the morning after the first close 3% above the buy price; stop 2.5xATR; out "
                                    "after 20 sessions. One at a time.",
                               profit_close_pct=0.03, max_open=1, goal_exempt=True)


def _init(stats):
    B._init(stats)
    B._G["plus_stats"] = {**B._G["stats"], "D2": stats}
    B._G["libs"]["PLUS"] = B._G["libs"]["TODAY"] + (d2_setup(),)


def one(job):
    r = B.one(job)
    return r


def main():
    from tradeagent.config import load_config
    from tradeagent.setups.simulate import simulate_swing
    from tradeagent.setups.stats import compute_stats
    cfg = load_config()
    bars = B.load_bars()
    s = d2_setup()
    trades = []
    for sym in s.universe:
        trades += [t for t in simulate_swing(bars[sym].loc[:"2025-12-31"], s, sym, cfg.backtest.round_trip_cost)
                   if t.entry_date >= pd.Timestamp("2015-01-01") and t.reason != "end"]
    st = compute_stats(s, trades, len(s.universe), cfg)
    tdf = pd.DataFrame([t.__dict__ for t in trades])
    res = {"step1": st.as_dict()}
    res["step1"]["exits"] = tdf.reason.value_counts().to_dict()
    res["step1"]["avg_hold"] = float(tdf.hold_days.mean())
    keys = ("n", "in_metric", "out_n", "out_metric", "loss_rate", "tail_ret", "exp_r", "edge", "confidence", "tier",
            "evidence_note", "recommendable", "exits", "avg_hold")
    print("STEP 1:", json.dumps({k: res["step1"][k] for k in keys}, default=str))
    if not st.recommendable:
        res["result"] = "FAILED step 1"
    else:
        jobs = [(v, x, (pd.Timestamp(x) + pd.DateOffset(months=24)).date().isoformat()) for x in B.STARTS for v in ("TODAY", "PLUS")]
        jobs += [(v, "2026-01-02", "2026-11-20") for v in ("TODAY", "PLUS")]
        with ProcessPoolExecutor(12, initializer=_init, initargs=(st.as_dict(),)) as ex:
            out = pd.DataFrame(list(ex.map(one, jobs)))
        out = out.rename(columns={"d1_trades": "dip_trades", "d1_pnl": "dip_pnl"})
        out.to_csv(OUT / "big_dip_d2_accounts.csv", index=False)
        a = out[out.start != "2026-01-02"].pivot(index="start", columns="variant", values=["gain", "worst"])
        diff, dd = a["gain"]["PLUS"] - a["gain"]["TODAY"], a["worst"]["PLUS"] - a["worst"]["TODAY"]
        ok2 = (diff > 1e-9).mean() >= 0.6 and diff.median() > 0 and dd.median() >= -1
        f = out[out.start == "2026-01-02"].set_index("variant")
        g26 = float(f.at["PLUS", "gain"] - f.at["TODAY", "gain"])
        plus = out[(out.variant == "PLUS") & (out.start != "2026-01-02")]
        res["step2"] = {"better_share": float((diff > 1e-9).mean()), "median_gain_pts": float(diff.median()),
                        "median_drop_pts": float(dd.median()), "passed": bool(ok2),
                        "dip_trades_median": float(plus.dip_trades.median()), "dip_pnl_median": float(plus.dip_pnl.median()),
                        "dip_pnl_positive_share": float((plus.dip_pnl > 0).mean())}
        res["step3"] = {"gain_2026_pts": g26, "passed": g26 >= -1}
        res["result"] = "PASSED all steps" if ok2 and g26 >= -1 else ("FAILED step 2" if not ok2 else "FAILED step 3")
        print("STEP 2:", res["step2"], "\nSTEP 3:", res["step3"])
    print("RESULT:", res["result"])
    (OUT / "big_dip_d2_study.json").write_text(json.dumps(res, indent=1, default=str))


if __name__ == "__main__":
    main()
