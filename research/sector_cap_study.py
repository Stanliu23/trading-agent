"""Sector cap for the momentum experiment (rules fixed in research/ideas_ledger.json, idea 2026-11-23-5, before running).

Momentum as running (top 10 of 77 by 12-1 month return, 10% each, monthly) vs the same with at most 3 from one GICS
sector. Whole account in the strategy, 36 quarterly starts Apr 2015 - Jan 2024, 24 months, $300 + $250/month, 0.1%
round trip, idle cash in BIL. Pass: (a) better in >= 60% of starts, median gain > 0, median worst drop no more than
1 point deeper; or (b) median worst drop >= 1 point shallower and median gain no more than 1 point lower.

Sectors: today's GICS sectors, applied to the whole history (small bias: some companies changed sector).
Run:  uv run python research/sector_cap_study.py
"""

import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import strategy_tournament as T  # noqa: E402  (same engine and data as the tournament)

OUT = T.ROOT / "research" / "results"
CAP = 3
SECTOR = {
    **dict.fromkeys(["AAPL", "MSFT", "NVDA", "CSCO", "ORCL", "ADBE", "CRM", "INTC", "AMD", "QCOM", "TXN", "AVGO", "MU",
                     "AMAT", "LRCX", "KLAC", "ADI", "MRVL", "NXPI", "INTU", "NOW", "IBM", "ACN"], "Information Technology"),
    **dict.fromkeys(["GOOGL", "META", "NFLX", "DIS", "T", "VZ", "CMCSA"], "Communication Services"),
    **dict.fromkeys(["AMZN", "HD", "MCD", "NKE", "LOW", "SBUX", "BKNG"], "Consumer Discretionary"),
    **dict.fromkeys(["PG", "KO", "PEP", "COST", "WMT", "TGT"], "Consumer Staples"),
    **dict.fromkeys(["JPM", "V", "MA", "BAC", "WFC", "GS", "MS", "BLK", "AXP"], "Financials"),
    **dict.fromkeys(["UNH", "JNJ", "MRK", "ABBV", "PFE", "LLY", "TMO", "AMGN", "GILD", "BMY", "ISRG"], "Health Care"),
    **dict.fromkeys(["XOM", "CVX", "COP", "SLB"], "Energy"),
    **dict.fromkeys(["UNP", "CAT", "DE", "HON", "GE", "LMT", "RTX"], "Industrials"),
    **dict.fromkeys(["NEE", "DUK"], "Utilities"),
    "LIN": "Materials",
}


def weights_mom_capped(C, stocks):
    out = {}
    for d in T._period_ends(C.index, "M"):
        i = C.index.get_loc(d)
        if i < 252:
            continue
        r = (C[stocks].iloc[i - 21] / C[stocks].iloc[i - 252] - 1).dropna().sort_values(ascending=False)
        picks, count = [], {}
        for s in r.index:
            if count.get(SECTOR[s], 0) < CAP:
                picks.append(s)
                count[SECTOR[s]] = count.get(SECTOR[s], 0) + 1
            if len(picks) == 10:
                break
        out[d] = pd.Series(0.1, index=picks)
    return out


def main():
    from tradeagent.setups.library import TRADED_STOCKS
    assert set(TRADED_STOCKS) <= set(SECTOR), set(TRADED_STOCKS) - set(SECTOR)
    bars = T.load()
    cal_all = bars["SPY"].loc["2014-01-01":T.END].index
    C = pd.DataFrame({s: bars[s]["close"] for s in bars}).reindex(cal_all).ffill()
    O = pd.DataFrame({s: bars[s]["open"] for s in bars}).reindex(cal_all).fillna(C)
    bil = bars["BIL"]["close"].reindex(cal_all).pct_change()
    stocks = [s for s in TRADED_STOCKS if s in C]
    W = {"uncapped": T.weights_mom(C, stocks), "capped": weights_mom_capped(C, stocks)}
    rows = []
    for st in T.STARTS:
        en = (pd.Timestamp(st) + pd.DateOffset(months=24)).date().isoformat()
        cal = cal_all[(cal_all >= st) & (cal_all <= en)]
        dep = T.deposits_for(cal)
        for k, w in W.items():
            g, dd = T.account_stats(T.run_weights(w, O, C, bil, cal, dep), dep)
            rows.append({"start": st, "variant": k, "gain": g * 100, "worst": dd * 100})
    df = pd.DataFrame(rows).pivot(index="start", columns="variant", values=["gain", "worst"])
    diff, dd = df["gain"]["capped"] - df["gain"]["uncapped"], df["worst"]["capped"] - df["worst"]["uncapped"]
    a = (diff > 1e-9).mean() >= 0.6 and diff.median() > 0 and dd.median() >= -1
    b = dd.median() >= 1 and diff.median() >= -1
    cal = cal_all[(cal_all >= "2026-01-02") & (cal_all <= T.END)]
    dep = T.deposits_for(cal)
    f26 = {k: T.account_stats(T.run_weights(w, O, C, bil, cal, dep), dep) for k, w in W.items()}
    last = max(W["capped"])
    res = {"better_share": float((diff > 1e-9).mean()), "median_gain_pts": float(diff.median()),
           "median_drop_pts": float(dd.median()), "uncapped_median_gain": float(df["gain"]["uncapped"].median()),
           "uncapped_median_worst": float(df["worst"]["uncapped"].median()),
           "capped_median_gain": float(df["gain"]["capped"].median()), "capped_median_worst": float(df["worst"]["capped"].median()),
           "rule_a": bool(a), "rule_b": bool(b), "passed": bool(a or b),
           "2026_gain_pts": float((f26["capped"][0] - f26["uncapped"][0]) * 100),
           "2026_drop_pts": float((f26["capped"][1] - f26["uncapped"][1]) * 100),
           f"capped_picks_{last.date()}": list(W["capped"][last].index),
           f"uncapped_picks_{last.date()}": list(W["uncapped"][last].index)}
    df.round(2).to_csv(OUT / "sector_cap_starts.csv")
    (OUT / "sector_cap_study.json").write_text(json.dumps(res, indent=1))
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
