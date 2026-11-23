"""Volatility-scaled long-term bucket (rules fixed in research/ideas_ledger.json, idea 2026-11-23-1, before running).

Target long-term share = min(1, 15% / SPY 20-day realised volatility, annualised), read at each close; trade at the next
open only when the held share is 10+ points away, spread across the funds in proportion to what is held. Each deposit
buys the least-held core fund with (deposit x current target share), the rest stays cash (earning BIL). 0.1% round trip.
Account = long-term part x 40% + today's short-term part x 60% (the same short-term results from the real simulator on
both sides). Pass: 36 starts better in >= 60%, median gain > 0, median worst drop no more than 1 point deeper; 2026
must not trail today's rules by more than 1 point.

Run:  uv run python research/vol_scaling_study.py
"""

import json
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import strategy_tournament as T  # noqa: E402

OUT = T.ROOT / "research" / "results"
TARGET_VOL, BAND = 0.15, 0.10


def run_lt_scaled(O, C, core, cal, dep, bil, target):
    qty, cash, pending, vals, trades = {s: 0.0 for s in core}, 0.0, None, [], 0
    prior = target.loc[:cal[0]].iloc[:-1]
    share = float(prior.iloc[-1]) if len(prior) else 1.0                 # target known at the close before day 0
    for d in cal:
        o = O.loc[d]
        a = dep.get(d, 0.0)
        if a > 0:
            s = min(core, key=lambda x: qty[x] * o[x])
            qty[s] += a * share * (1 - T.COST) / o[s]
            cash += a * (1 - share)
        if pending is not None:
            inv = sum(q * o[s] for s, q in qty.items())
            value = inv + cash
            delta = pending * value - inv
            w = {s: qty[s] * o[s] / inv for s in core} if inv > 0 else {s: 1 / len(core) for s in core}
            if delta > 0:
                delta = min(delta, cash)
                for s in core:
                    qty[s] += delta * w[s] * (1 - T.COST) / o[s]
                cash -= delta
            else:
                for s in core:
                    sell = -delta * w[s]
                    qty[s] -= sell / o[s]
                    cash += sell * (1 - T.COST)
            trades += 1
            pending = None
        cash *= 1 + float(bil.get(d, 0.0) or 0.0)
        c = C.loc[d]
        inv = sum(q * c[s] for s, q in qty.items())
        value = inv + cash
        vals.append(value)
        share = float(target.get(d, share))
        held = inv / value if value > 0 else share
        if abs(held - share) >= BAND:
            pending = share
    return pd.Series(vals, index=cal), trades


def main():
    from tradeagent.setups.library import CORE_ETFS
    bars = T.load()
    cal_all = bars["SPY"].loc["2014-01-01":T.END].index
    C = pd.DataFrame({s: bars[s]["close"] for s in bars}).reindex(cal_all).ffill()
    O = pd.DataFrame({s: bars[s]["open"] for s in bars}).reindex(cal_all).fillna(C)
    bil = bars["BIL"]["close"].reindex(cal_all).pct_change()
    vol = C["SPY"].pct_change().rolling(20).std() * np.sqrt(252)
    target = (TARGET_VOL / vol).clip(upper=1.0).dropna()
    windows = [(s, (pd.Timestamp(s) + pd.DateOffset(months=24)).date().isoformat()) for s in T.STARTS]
    windows.append(("2026-01-02", T.END))
    jobs = [("TODAY", a, b, 300, 250) for a, b in windows]
    with ProcessPoolExecutor(12, initializer=T._init) as ex:
        st = {r[0][1]: r[1] for r in ex.map(T.today_sleeve, jobs)}
    rows = []
    for a, b in windows:
        cal = cal_all[(cal_all >= a) & (cal_all <= b)]
        dep = T.deposits_for(cal)
        stv = T.from_returns(st[a].reindex(cal, fill_value=0.0), dep)
        base = T.run_lt(O, C, list(CORE_ETFS), cal, dep)
        scaled, n_trades = run_lt_scaled(O, C, list(CORE_ETFS), cal, dep, bil, target)
        for k, lt in (("today", base), ("scaled", scaled)):
            g, dd = T.account_stats(lt * 0.4 + stv * 0.6, dep)
            rows.append({"start": a, "variant": k, "gain": g * 100, "worst": dd * 100,
                         "band_trades": n_trades if k == "scaled" else 0,
                         "avg_share": float((target.reindex(cal).ffill()).mean()) if k == "scaled" else 1.0})
    df = pd.DataFrame(rows)
    df.to_csv(OUT / "vol_scaling_accounts.csv", index=False)
    a = df[df.start != "2026-01-02"].pivot(index="start", columns="variant", values=["gain", "worst"])
    diff, dd = a["gain"]["scaled"] - a["gain"]["today"], a["worst"]["scaled"] - a["worst"]["today"]
    ok = (diff > 1e-9).mean() >= 0.6 and diff.median() > 0 and dd.median() >= -1
    f = df[df.start == "2026-01-02"].set_index("variant")
    g26 = float(f.at["scaled", "gain"] - f.at["today", "gain"])
    res = {"better_share": float((diff > 1e-9).mean()), "median_gain_pts": float(diff.median()),
           "median_drop_pts": float(dd.median()), "today_median_gain": float(a["gain"]["today"].median()),
           "today_median_worst": float(a["worst"]["today"].median()), "scaled_median_gain": float(a["gain"]["scaled"].median()),
           "scaled_median_worst": float(a["worst"]["scaled"].median()),
           "band_trades_median": float(df[(df.variant == "scaled") & (df.start != "2026-01-02")].band_trades.median()),
           "avg_target_share": float(target.loc["2015":"2025"].mean()),
           "step_36_passed": bool(ok), "gain_2026_pts": g26, "drop_2026_pts": float(f.at["scaled", "worst"] - f.at["today", "worst"]),
           "passed": bool(ok and g26 >= -1)}
    (OUT / "vol_scaling_study.json").write_text(json.dumps(res, indent=1))
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
