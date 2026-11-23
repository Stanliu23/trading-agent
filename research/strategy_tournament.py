"""Strategy tournament (Stanley's request, 2026-11-23): test 7 published short-term strategies against today's rules,
at several long/short splits and in different market conditions, then pick 1-2 for their own paper accounts.

Everything below was written down BEFORE any result was seen. Nothing here changes the live agent.

Candidates (short-term sleeve; published parameters, not tuned):
  MOM   Stock momentum (Jegadeesh-Titman): last session of each month, rank the 77 traded stocks by the return from
        12 months ago to 1 month ago; hold the top 10 equally from the next open.
  TREND ETF trend timing (Faber 2007): last session of each month, each of the 20 ETFs gets 1/20 of the sleeve if its
        month-end close is above its 10-month average of month-end closes, otherwise that slice is cash.
  DON   Donchian breakout (Turtle system 2): an ETF closing above its prior 55-day high is bought next open with
        1/10 of the sleeve (max 10, strongest 55-day return first); sold next open after a close below its prior
        20-day low or below entry - 2xATR(20).
  S3F   Today's rules with S3 bought only while SPY is above its 200-day average.
  SECT  Sector rotation: last session of each month, hold the 3 of the 9 sector SPDRs with the best 6-month return.
  REV   Short-term reversal (Lehmann 1990): last session of each week, hold the 5 traded stocks with the worst 5-day
        return, equally, for one week.
  LOWV  Low volatility (Blitz & van Vliet 2007): last session of each month, hold the 10 traded stocks with the lowest
        252-day volatility of daily returns, equally.
Shared: orders fill at the next open, 0.1% round-trip cost (0.05% each side), idle cash earns BIL (as today's
config), no leverage, long only.

Long-term sleeve for every account: L1 (each deposit buys whichever of VTI/QQQ/SCHD is held least, never sold).
Money: $300 then $250 each month (same as every earlier account test), split by the long/short ratio.
Accounts are built as LT sleeve x (1-r) + ST sleeve x r. Both sleeves are linear in money, so one run per sleeve
serves every ratio. Today's short-term sleeve comes from the real simulator (goal pause, setup switch, sizing) and is
applied through its daily time-weighted return.

Pass bar (same as every earlier change), judged at today's 40/60:
  1. the short-term sleeve makes a net profit after costs in BOTH design (2015-2023) and check (2024-2025);
  2. 36 starts (quarterly Apr 2015 - Jan 2024, 24 months each, so none reaches 2026): the account beats today's
     account in >= 60% of starts, the median gain is positive, the median worst drop is no more than 1 point deeper;
  3. final check, Jan-Nov 2026 (never looked at before): the sleeve does not lose money.
Pick rule: of the strategies passing all 3, up to 2 with the highest median gain in step 2. If none pass, none.
Ratios and market conditions are reported for every strategy; they do not change the pass/fail.

Run:  uv run python research/strategy_tournament.py        (writes research/results/)
"""

from __future__ import annotations

import dataclasses
import json
import sys
from concurrent.futures import ProcessPoolExecutor
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "research" / "results"
END = "2026-11-20"
COST = 0.0005
SECTORS = ["XLK", "XLF", "XLE", "XLV", "XLI", "XLY", "XLP", "XLU", "XLB"]
RATIOS = [(100, 0), (80, 20), (60, 40), (40, 60), (20, 80), (0, 100)]
STARTS = [d.date().isoformat() for d in pd.date_range("2015-04-01", "2024-01-01", freq="3MS")]
PERIODS = {"design": ("2015-01-02", "2023-12-31"), "check": ("2024-01-01", "2025-12-31"), "final": ("2026-01-01", END)}
EPISODES = {"2018 Q4 sell-off": ("2018-09-21", "2018-12-24"), "2020 crash": ("2020-02-20", "2020-03-23"),
            "2020 rebound": ("2020-03-24", "2020-08-31"), "2022 bear market": ("2022-01-04", "2022-10-12"),
            "2023 recovery": ("2022-10-13", "2023-12-29"), "2025 tariff sell-off": ("2025-02-20", "2025-04-08")}
STRATS = ["TODAY", "MOM", "TREND", "DON", "S3F", "SECT", "REV", "LOWV"]


def load():
    sys.path.insert(0, str(ROOT / "src"))
    from tradeagent import prices
    from tradeagent.setups import library as lib
    syms = sorted(set(lib.TRADED_STOCKS) | set(lib.ETFS) | set(lib.CORE_ETFS) | {"BIL", "^VIX"})
    bars, missing = prices.daily_bars(syms, "2014-01-01", END)
    assert not missing, missing
    return bars


def deposits_for(cal: pd.DatetimeIndex, first=300.0, monthly=250.0) -> pd.Series:
    d = pd.Series(0.0, index=cal)
    d.iloc[0] = first
    m = pd.Series(cal.to_period("M"), index=cal)
    d[(m != m.shift(1)) & (np.arange(len(cal)) > 0)] = monthly
    return d


# --- target weights (signal at a close, filled next open) ----------------------------------------------------------

def _period_ends(cal, freq):
    p = pd.Series(cal.to_period(freq), index=cal)
    return cal[(p != p.shift(-1)).to_numpy()]


def weights_mom(C, stocks):
    out = {}
    for d in _period_ends(C.index, "M"):
        i = C.index.get_loc(d)
        if i < 252:
            continue
        r = (C[stocks].iloc[i - 21] / C[stocks].iloc[i - 252] - 1).dropna()
        top = r.nlargest(10).index
        out[d] = pd.Series(0.1, index=top)
    return out


def weights_trend(C, etfs):
    out = {}
    ends = _period_ends(C.index, "M")
    me = C[etfs].loc[ends]
    sma10 = me.rolling(10, min_periods=10).mean()
    for d in ends:
        if sma10.loc[d].isna().all():
            continue
        on = (me.loc[d] > sma10.loc[d]) & sma10.loc[d].notna()
        out[d] = pd.Series(1 / len(etfs), index=on[on].index)
    return out


def weights_sect(C):
    out = {}
    for d in _period_ends(C.index, "M"):
        i = C.index.get_loc(d)
        if i < 126:
            continue
        r = (C[SECTORS].iloc[i] / C[SECTORS].iloc[i - 126] - 1).dropna()
        out[d] = pd.Series(1 / 3, index=r.nlargest(3).index)
    return out


def weights_rev(C, stocks):
    out = {}
    for d in _period_ends(C.index, "W"):
        i = C.index.get_loc(d)
        if i < 5:
            continue
        r = (C[stocks].iloc[i] / C[stocks].iloc[i - 5] - 1).dropna()
        out[d] = pd.Series(0.2, index=r.nsmallest(5).index)
    return out


def weights_lowv(C, stocks):
    out = {}
    rets = C[stocks].pct_change()
    for d in _period_ends(C.index, "M"):
        i = C.index.get_loc(d)
        if i < 252:
            continue
        v = rets.iloc[i - 251:i + 1].std().dropna()
        out[d] = pd.Series(0.1, index=v.nsmallest(10).index)
    return out


# --- sleeve engines -----------------------------------------------------------------------------------------------

def run_weights(W: dict, O, C, bil, cal, dep) -> pd.Series:
    """Rebalance to target weights at the next open after each signal close. Returns the sleeve value each close."""
    keys = sorted(W)
    cash, qty, pending, vals = 0.0, pd.Series(dtype=float), None, []
    prior = [k for k in keys if k < cal[0]]
    if prior:
        pending = W[prior[-1]]
    for d in cal:
        cash += dep.get(d, 0.0)
        if pending is not None:
            o = O.loc[d]
            held = (qty * o.reindex(qty.index)).fillna(0)
            value = cash + held.sum()
            tgt = (pending * value).reindex(pending.index)
            ok = o.reindex(tgt.index).notna()
            tgt = tgt[ok]
            allsyms = held.index.union(tgt.index)
            trade = (tgt.reindex(allsyms, fill_value=0) - held.reindex(allsyms, fill_value=0)).abs().sum()
            qty = tgt / o.reindex(tgt.index)
            cash = value - tgt.sum() - trade * COST
            pending = None
        cash *= 1 + float(bil.get(d, 0.0) or 0.0)
        vals.append(cash + float((qty * C.loc[d].reindex(qty.index)).fillna(0).sum()))
        if d in W:
            pending = W[d]
    return pd.Series(vals, index=cal)


def run_donchian(bars, etfs, O, C, bil, cal, dep) -> pd.Series:
    hi55 = C[etfs].shift(1).rolling(55).max()
    lo20 = C[etfs].shift(1).rolling(20).min()
    r55 = C[etfs] / C[etfs].shift(55) - 1
    atr20 = {}
    for s in etfs:
        df = bars[s]
        tr = pd.concat([df.high - df.low, (df.high - df.close.shift()).abs(), (df.low - df.close.shift()).abs()], axis=1).max(axis=1)
        atr20[s] = tr.rolling(20).mean()
    atr20 = pd.DataFrame(atr20)
    cash, pos, stop, buys, sells, vals = 0.0, {}, {}, [], [], []
    for d in cal:
        cash += dep.get(d, 0.0)
        o = O.loc[d]
        for s in sells:
            cash += pos.pop(s) * o[s] * (1 - COST)
            stop.pop(s, None)
        if buys:
            value = cash + sum(q * o[s] for s, q in pos.items())
            for s, st in buys:
                amt = min(value / 10, cash)
                if amt > 0 and np.isfinite(o[s]):
                    pos[s] = amt * (1 - COST) / o[s]
                    stop[s] = st
                    cash -= amt
        sells, buys = [], []
        cash *= 1 + float(bil.get(d, 0.0) or 0.0)
        c = C.loc[d]
        vals.append(cash + sum(q * c[s] for s, q in pos.items()))
        for s in list(pos):
            if c[s] < lo20.at[d, s] or c[s] < stop[s]:
                sells.append(s)
        free = 10 - (len(pos) - len(sells))
        cand = [s for s in etfs if s not in pos and np.isfinite(hi55.at[d, s]) and c[s] > hi55.at[d, s]]
        cand.sort(key=lambda s: -r55.at[d, s])
        buys = [(s, c[s] - 2 * atr20.at[d, s]) for s in cand[:max(free, 0)]]
    return pd.Series(vals, index=cal)


def run_lt(O, C, core, cal, dep) -> pd.Series:
    qty, vals = {s: 0.0 for s in core}, []
    for d in cal:
        a = dep.get(d, 0.0)
        if a > 0:
            o = O.loc[d]
            s = min(core, key=lambda x: qty[x] * o[x])
            qty[s] += a * (1 - COST) / o[s]
        vals.append(sum(q * C.at[d, s] for s, q in qty.items()))
    return pd.Series(vals, index=cal)


def from_returns(r: pd.Series, dep: pd.Series) -> pd.Series:
    """Sleeve value under deposit schedule dep, given its daily time-weighted returns r (r on day 0 ignored)."""
    v, out = 0.0, []
    for i, d in enumerate(dep.index):
        v = (v * (1 + r.iloc[i]) if i else 0.0) + dep.iloc[i]
        out.append(v)
    return pd.Series(out, index=dep.index)


def twr(value: pd.Series, inflow: pd.Series) -> pd.Series:
    """Daily time-weighted return; day 0 = 0."""
    prev = value.shift(1)
    r = ((value - inflow.reindex(value.index, fill_value=0)) / prev - 1).where(prev > 0, 0.0)
    r.iloc[0] = 0.0
    return r.fillna(0.0)


# --- today's rules (real simulator) --------------------------------------------------------------------------------

_G = {}


def _init():
    sys.path.insert(0, str(ROOT / "src"))
    import tradeagent.papertrade as pt
    from tradeagent.config import load_config
    from tradeagent.setups import library as lib
    bars = load()
    earn = {}
    for f in ("earn.json", "earn_full.json"):
        earn.update({k: [date.fromisoformat(x) for x in v]
                     for k, v in json.loads((ROOT / "data" / "research" / f).read_text()).items()})
    stats = {d["setup_id"]: d for d in json.loads((ROOT / "data" / "setup_stats.json").read_text())}
    spy = bars["SPY"]["close"]
    spy_up = spy > spy.rolling(200).mean()
    s3 = next(s for s in lib.LIBRARY if s.id == "S3")
    s3f = dataclasses.replace(s3, signal=lambda df, f=s3.signal: f(df) & spy_up.reindex(df.index).fillna(False))
    _G.update(pt=pt, cfg=load_config(), bars=bars, earn=earn, stats=stats,
              libs={"TODAY": lib.LIBRARY, "S3F": tuple(s3f if s.id == "S3" else s for s in lib.LIBRARY)})


def today_sleeve(job):
    """(variant, start, end, first, monthly) -> short-term sleeve daily TWR and the full account value."""
    variant, start, end, first, monthly = job
    pt = _G["pt"]
    pt.LIBRARY = _G["libs"][variant]
    sim = pt.simulate_with_goal_rules(_G["bars"], _G["cfg"], _G["stats"], start, end, first, monthly, _G["earn"])
    d = sim.daily
    st = d.st_value + d.cash_st
    inflow = pd.Series(sim.st_inflows, dtype=float)
    st_trades = [t for t in sim.trades if t.bucket == "short_term"]
    return job, twr(st, inflow), d.value, len(st_trades)


# --- main ---------------------------------------------------------------------------------------------------------

def account_stats(acct: pd.Series, dep: pd.Series) -> tuple[float, float]:
    total = dep.sum()
    r = twr(acct, dep.where(np.arange(len(dep)) > 0, 0.0))
    idx = (1 + r.iloc[1:]).cumprod()
    return (acct.iloc[-1] - total) / total, float((idx / idx.cummax() - 1).min()) if len(idx) else 0.0


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    bars = load()
    sys.path.insert(0, str(ROOT / "src"))
    from tradeagent.setups import library as lib
    cal_all = bars["SPY"].loc["2014-01-01":END].index
    C = pd.DataFrame({s: bars[s]["close"] for s in bars}).reindex(cal_all).ffill()
    O = pd.DataFrame({s: bars[s]["open"] for s in bars}).reindex(cal_all)
    O = O.fillna(C)
    bil = bars["BIL"]["close"].reindex(cal_all).pct_change()
    stocks = [s for s in lib.TRADED_STOCKS if s in C]
    W = {"MOM": weights_mom(C, stocks), "TREND": weights_trend(C, lib.ETFS), "SECT": weights_sect(C),
         "REV": weights_rev(C, stocks), "LOWV": weights_lowv(C, stocks)}

    def sleeve(name, cal, dep):
        if name == "DON":
            return run_donchian(bars, lib.ETFS, O, C, bil, cal, dep)
        return run_weights(W[name], O, C, bil, cal, dep)

    # Today's rules and S3F through the real simulator, in parallel.
    jobs = []
    for v in ("TODAY", "S3F"):
        jobs += [(v, s, (pd.Timestamp(s) + pd.DateOffset(months=24)).date().isoformat(), 300, 250) for s in STARTS]
        jobs += [(v, a, b, 1000, 0) for a, b in PERIODS.values()]
        jobs.append((v, "2015-01-02", END, 1000, 0))
    print(len(jobs), "simulator runs", flush=True)
    with ProcessPoolExecutor(12, initializer=_init) as ex:
        sim = {r[0]: r[1:] for r in ex.map(today_sleeve, jobs)}
    print("simulator done", flush=True)

    # Step 1: net profit of the short-term sleeve per period ($1,000, no deposits).
    rows = []
    for pname, (a, b) in PERIODS.items():
        cal = cal_all[(cal_all >= a) & (cal_all <= b)]
        dep = pd.Series(0.0, index=cal)
        dep.iloc[0] = 1000.0
        for s in STRATS:
            if s in ("TODAY", "S3F"):
                r, _, n = sim[(s, a, b, 1000, 0)]
                v = from_returns(r.reindex(cal, fill_value=0.0), dep)
            else:
                v = sleeve(s, cal, dep)
            rows.append({"strategy": s, "period": pname, "from": a, "to": b, "end_value": round(v.iloc[-1], 2),
                         "net_profit_pct": round((v.iloc[-1] / 1000 - 1) * 100, 2)})
    step1 = pd.DataFrame(rows)
    step1.to_csv(OUT / "step1_periods.csv", index=False)

    # Step 2: 36 starts x ratios.
    rows = []
    for st in STARTS:
        en = (pd.Timestamp(st) + pd.DateOffset(months=24)).date().isoformat()
        cal = cal_all[(cal_all >= st) & (cal_all <= en)]
        dep = deposits_for(cal)
        lt = run_lt(O, C, lib.CORE_ETFS, cal, dep)
        for s in STRATS:
            if s in ("TODAY", "S3F"):
                r, real_acct, _ = sim[(s, st, en, 300, 250)]
                stv = from_returns(r.reindex(cal, fill_value=0.0), dep)
            else:
                stv = sleeve(s, cal, dep)
            for lr, sr in RATIOS:
                acct = lt * lr / 100 + stv * sr / 100
                gain, drop = account_stats(acct, dep)
                rows.append({"start": st, "strategy": s, "ratio": f"{lr}/{sr}", "gain_pct": gain * 100,
                             "worst_drop_pct": drop * 100})
            if s == "TODAY":
                g, dd = account_stats(real_acct.reindex(cal).ffill(), dep)
                rows.append({"start": st, "strategy": "TODAY_REAL_SIM", "ratio": "40/60", "gain_pct": g * 100,
                             "worst_drop_pct": dd * 100})
    step2 = pd.DataFrame(rows)
    step2.to_csv(OUT / "step2_starts.csv", index=False)

    # Market conditions: one continuous run per sleeve, $1,000 from Jan 2015, daily returns by condition.
    cal = cal_all[(cal_all >= "2015-01-02") & (cal_all <= END)]
    dep = pd.Series(0.0, index=cal)
    dep.iloc[0] = 1000.0
    daily = {}
    for s in STRATS:
        if s in ("TODAY", "S3F"):
            daily[s] = sim[(s, "2015-01-02", END, 1000, 0)][0].reindex(cal, fill_value=0.0)
        else:
            daily[s] = twr(sleeve(s, cal, dep), pd.Series(0.0, index=cal))
    daily["L1 (index funds)"] = twr(run_lt(O, C, lib.CORE_ETFS, cal, dep), pd.Series(0.0, index=cal))
    daily["SPY"] = C["SPY"].reindex(cal).pct_change().fillna(0.0)
    R = pd.DataFrame(daily)
    R.to_csv(OUT / "daily_returns.csv")
    spy = C["SPY"]
    vix = C["^VIX"]
    up = (spy > spy.rolling(200).mean()).shift(1).reindex(cal).fillna(False)
    stress = (vix > vix.rolling(252, min_periods=200).quantile(0.8)).shift(1).reindex(cal).fillna(False)
    conds = {"SPY above 200-day": up, "SPY below 200-day": ~up, "Calm (VIX normal)": ~stress,
             "Stress (VIX top 20%)": stress}
    rows = []
    for k, m in conds.items():
        for s in R:
            x = R.loc[m.to_numpy(), s]
            rows.append({"condition": k, "strategy": s, "days": len(x),
                         "annualised_pct": ((1 + x).prod() ** (252 / max(len(x), 1)) - 1) * 100})
    for k, (a, b) in EPISODES.items():
        for s in R:
            x = R.loc[a:b, s]
            idx = (1 + x).cumprod()
            rows.append({"condition": k, "strategy": s, "days": len(x), "total_pct": (idx.iloc[-1] - 1) * 100,
                         "worst_drop_pct": float((idx / idx.cummax() - 1).min()) * 100})
    pd.DataFrame(rows).to_csv(OUT / "conditions.csv", index=False)
    print("DONE", flush=True)


if __name__ == "__main__":
    main()
