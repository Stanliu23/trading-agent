"""Big-dip rebound D1 (rules fixed in research/ideas_ledger.json, idea 2026-11-23-4, before running).

Step 1: the standard setup evidence bar (as S1-S4). Step 2: 36-start account test, today's rules + D1 vs today's
rules. Step 3: Jan-Nov 2026 must not trail by more than 1 point. Steps 2-3 run only if step 1 passes.

Run:  uv run python research/big_dip_study.py
"""

import dataclasses
import json
import sys
from concurrent.futures import ProcessPoolExecutor
from datetime import date
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "research" / "results"
STARTS = [d.date().isoformat() for d in pd.date_range("2015-04-01", "2024-01-01", freq="3MS")]


def d1_setup():
    from tradeagent.setups.library import Setup, TRADED_STOCKS

    def signal(df):
        c = df["close"]
        level = 0.70 * c.rolling(60, min_periods=60).max()
        return (c <= level) & (c.shift(1) > level.shift(1))

    return Setup(id="D1", name="Big-dip rebound", bucket="short_term", kind="swing", universe=tuple(TRADED_STOCKS),
                 rule="A stock's first close 30% or more below its highest close of the last 60 sessions. Stop 2.5xATR, "
                      "exit after 20 sessions.",
                 logic="Large caps that fall 30% in a few weeks have often rebounded within a month.",
                 signal=signal, stop_atr=2.5, max_hold_days=20)


def load_bars():
    from tradeagent import prices
    from tradeagent.setups.library import CORE_ETFS, ETFS, TRADED_STOCKS
    bars, missing = prices.daily_bars(sorted(set(TRADED_STOCKS) | set(ETFS) | set(CORE_ETFS) | {"BIL", "^VIX"}),
                                      "2014-01-01", "2026-11-20")
    assert not missing, missing
    return bars


_G = {}


def _init(d1_stats):
    import tradeagent.papertrade as pt
    from tradeagent.config import load_config
    from tradeagent.setups import library as lib
    earn = {}
    for f in ("earn.json", "earn_full.json"):
        earn.update({k: [date.fromisoformat(x) for x in v]
                     for k, v in json.loads((ROOT / "data" / "research" / f).read_text()).items()})
    stats = {d["setup_id"]: d for d in json.loads((ROOT / "data" / "setup_stats.json").read_text())}
    _G.update(pt=pt, cfg=load_config(), bars=load_bars(), earn=earn, stats=stats,
              plus_stats={**stats, "D1": d1_stats}, libs={"TODAY": lib.LIBRARY, "PLUS": lib.LIBRARY + (d1_setup(),)})


def one(job):
    variant, start, end = job
    pt = _G["pt"]
    pt.LIBRARY = _G["libs"][variant]
    stats = _G["plus_stats"] if variant == "PLUS" else _G["stats"]
    sim = pt.simulate_with_goal_rules(_G["bars"], _G["cfg"], stats, start, end, 300, 250, _G["earn"])
    d = sim.daily
    dep = sum(a for _, a, _ in sim.deposits)
    dp = pd.Series({x: a for x, a, _ in sim.deposits[1:]}, dtype=float).reindex(d.index, fill_value=0)
    idx = (1 + ((d.value - dp) / d.value.shift(1) - 1).iloc[1:]).cumprod()
    d1 = [t for t in sim.trades if t.setup_id in ("D1", "D2")]
    return {"variant": variant, "start": start, "gain": (d.value.iloc[-1] - dep) / dep * 100,
            "worst": float((idx / idx.cummax() - 1).min()) * 100, "d1_trades": len(d1), "d1_pnl": sum(t.pnl for t in d1)}


def main():
    sys.path.insert(0, str(ROOT / "src"))
    from tradeagent.config import load_config
    from tradeagent.setups.simulate import simulate_swing
    from tradeagent.setups.stats import compute_stats
    cfg = load_config()
    bars = load_bars()
    s = d1_setup()
    trades, tested = [], 0
    for sym in s.universe:
        df = bars[sym].loc[:"2025-12-31"]
        tested += 1
        trades += [t for t in simulate_swing(df, s, sym, cfg.backtest.round_trip_cost)
                   if t.entry_date >= pd.Timestamp("2015-01-01") and t.reason != "end"]
    st = compute_stats(s, trades, tested, cfg)
    res = {"step1": {k: v for k, v in st.as_dict().items()}}
    tdf = pd.DataFrame([t.__dict__ for t in trades])
    res["step1"]["trades_by_year"] = tdf.groupby(tdf.entry_date.dt.year).size().to_dict()
    res["step1"]["mean_r_by_year"] = tdf.groupby(tdf.entry_date.dt.year).r.mean().round(3).to_dict()
    print("STEP 1:", json.dumps({k: res["step1"][k] for k in ("n", "in_n", "in_metric", "out_n", "out_metric", "loss_rate",
                                                               "tail_ret", "exp_r", "edge", "confidence", "tier",
                                                               "passes_evidence", "evidence_note", "recommendable")}, default=str))
    print("trades by year:", res["step1"]["trades_by_year"], "\nmean R by year:", res["step1"]["mean_r_by_year"])
    if not st.recommendable:
        res["result"] = "FAILED step 1 (setup evidence bar)"
    else:
        jobs = [(v, x, (pd.Timestamp(x) + pd.DateOffset(months=24)).date().isoformat()) for x in STARTS for v in ("TODAY", "PLUS")]
        jobs += [(v, "2026-01-02", "2026-11-20") for v in ("TODAY", "PLUS")]
        with ProcessPoolExecutor(12, initializer=_init, initargs=(st.as_dict(),)) as ex:
            out = pd.DataFrame(list(ex.map(one, jobs)))
        out.to_csv(OUT / "big_dip_accounts.csv", index=False)
        a = out[out.start != "2026-01-02"].pivot(index="start", columns="variant", values=["gain", "worst"])
        diff, dd = a["gain"]["PLUS"] - a["gain"]["TODAY"], a["worst"]["PLUS"] - a["worst"]["TODAY"]
        ok2 = (diff > 1e-9).mean() >= 0.6 and diff.median() > 0 and dd.median() >= -1
        f = out[out.start == "2026-01-02"].set_index("variant")
        g26 = float(f.at["PLUS", "gain"] - f.at["TODAY", "gain"])
        res["step2"] = {"better_share": float((diff > 1e-9).mean()), "median_gain_pts": float(diff.median()),
                        "median_drop_pts": float(dd.median()), "passed": bool(ok2),
                        "d1_trades_median": float(out[out.variant == "PLUS"].d1_trades.median())}
        res["step3"] = {"gain_2026_pts": g26, "passed": g26 >= -1}
        res["result"] = "PASSED all steps" if ok2 and g26 >= -1 else ("FAILED step 2" if not ok2 else "FAILED step 3")
        print("STEP 2:", res["step2"], "\nSTEP 3:", res["step3"])
    print("RESULT:", res["result"])
    (OUT / "big_dip_study.json").write_text(json.dumps(res, indent=1, default=str))


if __name__ == "__main__":
    main()
