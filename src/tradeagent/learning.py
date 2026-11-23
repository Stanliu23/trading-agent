"""Learning from the paper accounts: the fill tracker and the fixed questions Q1-Q9 (docs/LEARNING.md).

Everything here MEASURES and REPORTS. Nothing places, changes or cancels an order, and no answer changes a rule by
itself. Questions, minimums and pass rules were fixed on 2026-11-23 before any paper data existed.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Optional
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from tradeagent.config import PROJECT_ROOT
from tradeagent.emailer import Line

NY = ZoneInfo("America/New_York")
START = date(2026, 11, 19)                     # paper test start: live data counts from here
ASSUMED_ROUND_TRIP = 0.001                     # what every backtest assumes (config backtest.round_trip_cost)
Z90 = 1.645
MIN = {"Q1": 30, "Q2": 10, "Q3": 2, "Q4": 10, "Q5": 20, "Q6": 5, "Q7": 20, "Q8": 30}
TITLES = {"Q1": "Trading cost", "Q2": "Stop fills", "Q3": "How often setups fire", "Q4": "Your moves",
          "Q5": "Rebalance timing", "Q6": "Experiments vs luck", "Q7": "Per-setup switch",
          "Q8": "Live vs backtest results", "Q9": "Runs and orders"}
REFERENCE = PROJECT_ROOT / "research" / "results" / "live_reference.json"
LUCK = PROJECT_ROOT / "research" / "results" / "daily_returns.csv"
SRC = "paper fills + fixed rules (docs/LEARNING.md)"


# --- the fill tracker -------------------------------------------------------------------------------------------------

def _ny(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(NY)


def assumed(purpose: str, side: str, bar: pd.Series, pre_open: bool, stop=None, target=None) -> tuple:
    """(assumed price, basis, question) for one fill, by the simulator's own conventions."""
    o, c = float(bar["open"]), float(bar["close"])
    if purpose == "stop" and stop is not None:
        return (o, "open (gapped below the stop)", "Q2") if o <= stop else (float(stop), "stop", "Q2")
    if purpose == "target" and target is not None:
        return (o, "open (gapped above the target)", "") if o >= target else (float(target), "target", "")
    if purpose == "time":
        return c, "close", "Q1"
    if purpose == "rebalance" and side == "buy":
        return o, "open (bought after the sells filled)", "Q5"
    if purpose in ("entry", "signal", "rebalance"):
        return (o, "open", "Q1") if pre_open else (None, "sent after the open: not counted", "")
    return None, "unknown purpose", ""


def cost_pct(side: str, fill: float, assumed_px: float) -> float:
    """Positive = worse for us than the simulator assumed."""
    return fill / assumed_px - 1 if side == "buy" else 1 - fill / assumed_px


def record_fills(conn, account: str, orders: list[dict], bars: dict, prefix: str,
                 intents: Optional[dict] = None) -> int:
    """Log every filled agent order not logged yet whose day's price bar exists. Returns how many were added."""
    have = {r[0] for r in conn.execute("SELECT order_id FROM fill_log")}
    by_cid = {o.get("client_order_id"): o for o in orders}
    n = 0
    for o in orders:
        cid = o.get("client_order_id") or ""
        oid = o.get("id") or cid
        if not cid.startswith(prefix) or oid in have or float(o.get("filled_qty") or 0) <= 0 \
                or not o.get("filled_avg_price") or not o.get("filled_at"):
            continue
        filled = _ny(o["filled_at"])
        day = pd.Timestamp(filled.date())
        df = bars.get(o["symbol"])
        if df is None or day not in df.index:
            continue                                   # bar not there yet: try again at the next close
        sub = _ny(o.get("submitted_at") or o["filled_at"])
        pre_open = sub.date() < filled.date() or sub.time() < time(9, 30)
        it = (intents or {}).get(cid, {})
        purpose = it.get("purpose") or ("rebalance" if account != "main" else "entry")
        lot = (intents or {}).get(it.get("lot_ref") or "", {})
        stop, target = lot.get("stop"), lot.get("target")
        entry_order = by_cid.get(it.get("lot_ref") or "")
        lot_entry = float(entry_order["filled_avg_price"]) if entry_order and entry_order.get("filled_avg_price") else None
        fill = float(o["filled_avg_price"])
        px, basis, q = assumed(purpose, o["side"], df.loc[day], pre_open, stop, target)
        conn.execute("INSERT INTO fill_log(order_id, account, client_order_id, symbol, side, purpose, submitted_at, "
                     "filled_at, day, qty, fill, assumed, basis, cost_pct, question, lot_entry, lot_stop) "
                     "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                     (oid, account, cid, o["symbol"], o["side"], purpose, sub.isoformat(timespec="seconds"),
                      filled.isoformat(timespec="seconds"), day.date().isoformat(), float(o["filled_qty"]), fill, px,
                      basis, cost_pct(o["side"], fill, px) if px else None, q, lot_entry, stop))
        n += 1
    conn.commit()
    return n


# --- answers ----------------------------------------------------------------------------------------------------------

@dataclass
class Answer:
    qid: str
    n: int
    need: Optional[int]
    status: str                                       # waiting | ok | flag
    text: str

    def line(self) -> Line:
        tone = {"flag": "down", "waiting": "muted"}.get(self.status)
        return Line(f"{self.qid} {TITLES[self.qid]}: {self.text}", SRC, tone)


def _waiting(qid: str, n: int, unit: str) -> Answer:
    return Answer(qid, n, MIN[qid], "waiting", f"{n} of {MIN[qid]} {unit} so far; not judged until then.")


def _mean_range(x: pd.Series) -> tuple[float, float, float]:
    m = float(x.mean())
    se = float(x.std(ddof=1) / math.sqrt(len(x))) if len(x) > 1 else float("inf")
    return m, m - Z90 * se, m + Z90 * se


def q1_cost(conn) -> Answer:
    x = pd.Series([r[0] for r in conn.execute("SELECT cost_pct FROM fill_log WHERE question='Q1' AND cost_pct IS NOT NULL")],
                  dtype=float)
    if len(x) < MIN["Q1"]:
        return _waiting("Q1", len(x), "counted fills")
    m, lo, hi = _mean_range(x)
    rt, rlo, rhi = 2 * m, 2 * lo, 2 * hi
    if rlo > ASSUMED_ROUND_TRIP:
        return Answer("Q1", len(x), MIN["Q1"], "flag", f"round trip {rt:.2%} (90% range {rlo:.2%} to {rhi:.2%}) over "
                      f"{len(x)} fills: HIGHER than the 0.10% every backtest assumes.")
    word = "lower than" if rhi < ASSUMED_ROUND_TRIP else "consistent with"
    return Answer("Q1", len(x), MIN["Q1"], "ok", f"round trip {rt:.2%} (90% range {rlo:.2%} to {rhi:.2%}) over {len(x)} "
                  f"fills: {word} the 0.10% assumed" + (" (no change: the agent never loosens)." if word == "lower than" else "."))


def q2_stops(conn) -> Answer:
    rows = conn.execute("SELECT assumed, fill, lot_entry, lot_stop FROM fill_log WHERE question='Q2'").fetchall()
    x = pd.Series([(a - f) / (e - s) for a, f, e, s in rows if None not in (a, f, e, s) and e > s], dtype=float)
    if len(x) < MIN["Q2"]:
        return _waiting("Q2", len(x), "stop sells")
    m, lo, hi = _mean_range(x)
    flag = m > 0.10 and lo > 0
    return Answer("Q2", len(x), MIN["Q2"], "flag" if flag else "ok",
                  f"stops cost {m:+.2f}R more than the backtest's fill on average (90% range {lo:+.2f} to {hi:+.2f}R, "
                  f"{len(x)} stops)" + (": the 15-minute checks lose more than assumed." if flag else "."))


def _reference() -> dict:
    return json.loads(REFERENCE.read_text())["setups"] if REFERENCE.exists() else {}


def _full_months(today: date) -> list[pd.Period]:
    first = pd.Period(START, "M") + (0 if START.day == 1 else 1)
    last = pd.Period(today, "M") - 1
    return list(pd.period_range(first, last, freq="M")) if last >= first else []


def q3_frequency(bars: dict, today: date) -> Answer:
    from tradeagent.setups.library import get
    months = _full_months(today)
    if len(months) < MIN["Q3"]:
        return _waiting("Q3", len(months), "full months")
    ref, parts, flag = _reference(), [], False
    lo_d, hi_d = months[0].start_time, months[-1].end_time
    for sid, r in ref.items():
        s = get(sid)
        live = sum(int(s.signal(bars[sym]).fillna(False).astype(bool).loc[lo_d:hi_d].sum()) for sym in s.universe if sym in bars)
        hist = pd.Series(r["monthly_signals"], dtype=float).rolling(len(months)).sum().dropna()
        p5, p95 = hist.quantile(0.05), hist.quantile(0.95)
        out = live < p5 or live > p95
        flag |= out
        parts.append(f"{sid} {live} (backtest {p5:.0f}-{p95:.0f}{', OUTSIDE' if out else ''})")
    return Answer("Q3", len(months), MIN["Q3"], "flag" if flag else "ok",
                  f"signals over {len(months)} months: " + "; ".join(parts) + ".")


def rule_exit(df: pd.DataFrame, after: pd.Timestamp, entry_day: pd.Timestamp, stop=None, target=None, max_hold=None,
              exit_signal=None, include_after: bool = False) -> tuple[float, pd.Timestamp, str, bool]:
    """Where the rule would have exited a lot it still held after ``after`` (price, day, why, finished)."""
    days = df.index[(df.index >= after) if include_after else (df.index > after)]
    held_before = int(((df.index >= entry_day) & (df.index < days[0])).sum()) if len(days) else 0
    sig = exit_signal(df).fillna(False).astype(bool) if exit_signal else None
    for k, d in enumerate(days):
        o, h, l, c = (float(df.at[d, x]) for x in ("open", "high", "low", "close"))
        first = d == entry_day
        if stop is not None and not first and o <= stop:
            return o, d, "stop", True
        if stop is not None and l <= stop:
            return float(stop), d, "stop", True
        if target is not None and not first and o >= target:
            return o, d, "target", True
        if target is not None and h >= target:
            return float(target), d, "target", True
        if max_hold and held_before + k + 1 >= max_hold:
            return c, d, "time", True
        if sig is not None and bool(sig.get(d, False)) and k + 1 < len(days):
            return float(df.at[days[k + 1], "open"]), days[k + 1], "signal", True
    last = df.index[-1]
    return float(df.at[last, "close"]), last, "still open (latest close)", False


def q4_your_moves(book, intents: dict, bars: dict) -> Answer:
    from tradeagent.setups.library import get
    moves = []                                          # (dollars your move made vs the rule)
    for c in getattr(book, "closed", []):
        if c.reason != "you" or c.lot.symbol not in bars:
            continue
        lot, df = c.lot, bars[c.lot.symbol]
        sid = lot.setup_id if lot.setup_id not in ("YOU", "L1") else None
        px, _, _, _ = rule_exit(df, pd.Timestamp(c.exit_day), pd.Timestamp(lot.entry_day), lot.stop, lot.target,
                                lot.max_hold, get(sid).exit_signal if sid else None)
        moves.append(c.qty * (c.exit - px))
    for cid in getattr(book, "yours_cancelled", set()):
        it = intents.get(cid, {})
        if it.get("side") != "buy" or it.get("symbol") not in bars or not it.get("dollars"):
            continue
        df, day = bars[it["symbol"]], pd.Timestamp(it.get("session"))
        if day not in df.index:
            continue
        entry = float(df.at[day, "open"])
        sid = it.get("setup_id")
        px, _, _, _ = rule_exit(df, day, day, it.get("stop"), it.get("target"), it.get("max_hold"),
                                get(sid).exit_signal if sid and sid != "L1" else None, include_after=True)
        moves.append(-(it["dollars"] / entry) * (px - entry))     # you avoided the rule's trade
    if len(moves) < MIN["Q4"]:
        return _waiting("Q4", len(moves), "moves")
    x = pd.Series(moves, dtype=float)
    share, total = float((x > 0).mean()), float(x.sum())
    verdict = ("your moves helped" if share >= 0.6 and total > 0 else
               "your moves cost money" if share <= 0.4 and total < 0 else "mixed")
    return Answer("Q4", len(x), MIN["Q4"], "ok", f"{len(x)} moves, {share:.0%} beat the rule, together "
                  f"{total:+,.2f} dollars vs the rule: {verdict}.")


def q5_rebalance(conn) -> Answer:
    x = pd.Series([r[0] for r in conn.execute("SELECT cost_pct FROM fill_log WHERE question='Q5' AND cost_pct IS NOT NULL")],
                  dtype=float)
    if len(x) < MIN["Q5"]:
        return _waiting("Q5", len(x), "experiment buys")
    m, lo, hi = _mean_range(x)
    flag = m > 0.001 and lo > 0
    return Answer("Q5", len(x), MIN["Q5"], "flag" if flag else "ok",
                  f"buying after the sells fill costs {m:+.2%} vs the open on average (90% range {lo:+.2%} to {hi:+.2%})"
                  + (": waiting costs money." if flag else "."))


def q6_luck(conn, bars: dict, exps) -> list[Answer]:
    out = []
    if not LUCK.exists():
        return out
    hist = pd.read_csv(LUCK, index_col=0, parse_dates=True)
    spy = bars["SPY"]["close"]
    for e in exps:
        rows = conn.execute("SELECT day, equity FROM exp_daily WHERE exp_id=? ORDER BY day", (e,)).fetchall()
        start = conn.execute("SELECT value FROM meta WHERE key=?", (f"exp:{e}:start",)).fetchone()
        eq0 = conn.execute("SELECT value FROM meta WHERE key=?", (f"exp:{e}:start_equity",)).fetchone()
        if not rows or not start or not eq0:
            out.append(Answer("Q6", 0, MIN["Q6"], "waiting", f"{e}: not started yet."))
            continue
        s0 = spy.loc[:pd.Timestamp(start[0]) - pd.DateOffset(days=1)]
        n = int(((spy.index >= pd.Timestamp(start[0])) & (spy.index <= pd.Timestamp(rows[-1][0]))).sum())
        if n < MIN["Q6"] or s0.empty:
            out.append(Answer("Q6", n, MIN["Q6"], "waiting", f"{e}: {n} of {MIN['Q6']} sessions so far."))
            continue
        ex = math.log(rows[-1][1] / float(eq0[0])) - math.log(float(spy.loc[:pd.Timestamp(rows[-1][0])].iloc[-1] / s0.iloc[-1]))
        band = (np.log1p(hist[e]) - np.log1p(hist["SPY"])).rolling(n).sum().dropna()
        lo, hi = band.quantile(0.05), band.quantile(0.95)
        flag = ex < lo or ex > hi
        out.append(Answer("Q6", n, MIN["Q6"], "flag" if flag else "ok",
                          f"{e} {math.expm1(ex):+.1%} vs SPY over {n} sessions; luck alone gives {math.expm1(lo):+.1%} to "
                          f"{math.expm1(hi):+.1%}" + (": OUTSIDE luck." if flag else ": within luck, tells us nothing yet.")))
    return out


def paper_trades(bars: dict, config) -> pd.DataFrame:
    """Every S2/S3/S4 signal traded on paper with the current exits (as the per-setup switch sees them)."""
    from tradeagent.setups.library import LIBRARY
    from tradeagent.setups.simulate import simulate
    rows = []
    for s in LIBRARY:
        if s.id not in ("S2", "S3", "S4"):
            continue
        for sym in s.universe:
            df = bars.get(sym)
            if df is None:
                continue
            for t in simulate(df, s, sym, config.backtest.round_trip_cost, 252):
                i = df.index.get_loc(t.entry_date)
                if i > 0 and t.r is not None:
                    rows.append({"setup_id": s.id, "signal_day": df.index[i - 1], "exit": t.exit_date, "r": t.r,
                                 "closed": t.reason != "end"})
    return pd.DataFrame(rows, columns=["setup_id", "signal_day", "exit", "r", "closed"])


def q7_switch(trades: pd.DataFrame, config) -> Answer:
    n_last, min_r = config.setup_switch.last_n_trades, config.setup_switch.min_avg_r
    live = trades[(trades.signal_day >= pd.Timestamp(START)) & trades.closed]
    off = []
    for _, t in live.iterrows():
        past = trades[(trades.setup_id == t.setup_id) & trades.closed & (trades.exit < t.signal_day)].sort_values("exit")
        recent = past.r.tail(n_last)
        off.append(len(recent) == n_last and recent.mean() < min_r)
    live = live.assign(off=off)
    sk, tk = live[live.off], live[~live.off]
    n = min(len(sk), len(tk))
    if n < MIN["Q7"]:
        return Answer("Q7", n, MIN["Q7"], "waiting", f"{len(sk)} skipped and {len(tk)} taken paper trades so far; "
                      f"not judged until {MIN['Q7']} of each.")
    d = float(sk.r.mean() - tk.r.mean())
    status, word = (("ok", "the switch skipped worse trades: it helped") if d < -0.1 else
                    ("flag", "the switch skipped BETTER trades") if d > 0.1 else ("ok", "no clear difference yet"))
    return Answer("Q7", n, MIN["Q7"], status, f"skipped {sk.r.mean():+.2f}R vs taken {tk.r.mean():+.2f}R "
                  f"({len(sk)} / {len(tk)} trades): {word}.")


def q8_live_vs_backtest(trades: pd.DataFrame) -> Answer:
    ref = _reference()
    live = trades[(trades.signal_day >= pd.Timestamp(START)) & trades.closed]
    parts, flag, judged = [], False, 0
    for sid, r in ref.items():
        x = live[live.setup_id == sid].r
        if len(x) < MIN["Q8"]:
            parts.append(f"{sid} {len(x)} of {MIN['Q8']}")
            continue
        judged += 1
        floor = r["r_mean"] - 2 * r["r_sd"] / math.sqrt(len(x))
        below = x.mean() < floor
        flag |= below
        parts.append(f"{sid} {x.mean():+.2f}R vs backtest {r['r_mean']:+.2f}R over {len(x)}"
                     + (" (BELOW the backtest beyond luck)" if below else ""))
    status = "flag" if flag else ("ok" if judged else "waiting")
    return Answer("Q8", judged, None, status, "; ".join(parts) + ("." if judged else "; not judged until then."))


def q9_operations(conn, today: date, now: datetime) -> Answer:
    from tradeagent import market_calendar
    first = conn.execute("SELECT MIN(substr(started_at,1,10)) FROM runs WHERE kind IN ('premarket','close','intraday')").fetchone()[0]
    missing = []
    if first:
        d = max(date.fromisoformat(first), START)
        while d <= today:
            sess = market_calendar.session(d)
            if sess:
                kinds = {r[0] for r in conn.execute("SELECT kind FROM runs WHERE substr(started_at,1,10)=? AND status IN "
                                                    "('ok','quiet')", (d.isoformat(),))}
                for k, due in (("premarket", time(9, 30)), ("close", time(17, 0))):
                    if k not in kinds and (d < today or now.astimezone(NY).time() > due):
                        missing.append(f"{k} {d:%b %d}")
            d = date.fromordinal(d.toordinal() + 1)
    failed = sum(conn.execute(f"SELECT COUNT(*) FROM {t} WHERE status='failed'").fetchone()[0]
                 for t in ("paper_intents", "exp_intents"))
    if missing or failed:
        return Answer("Q9", len(missing) + failed, None, "flag",
                      (f"missed runs: {', '.join(missing[:6])}{' …' if len(missing) > 6 else ''}. " if missing else "")
                      + (f"{failed} agent order(s) failed to send." if failed else ""))
    return Answer("Q9", 0, None, "ok", "no missed premarket or close runs and no failed orders since the start.")


def answers(conn, bars: dict, config, today: date, now: datetime, book=None, intents: Optional[dict] = None,
            exps=("MOM", "LOWV")) -> list[Answer]:
    out = [q1_cost(conn), q2_stops(conn), q3_frequency(bars, today),
           q4_your_moves(book, intents or {}, bars) if book is not None else
           Answer("Q4", 0, MIN["Q4"], "waiting", "the main Alpaca account could not be read this week."),
           q5_rebalance(conn)]
    out += q6_luck(conn, bars, exps)
    trades = paper_trades(bars, config)
    out += [q7_switch(trades, config), q8_live_vs_backtest(trades), q9_operations(conn, today, now)]
    return out


def store(conn, out: list[Answer], now: datetime) -> None:
    conn.executemany("INSERT OR REPLACE INTO learning_log(scored_at, qid, n, need, status, text) VALUES (?,?,?,?,?,?)",
                     [(now.isoformat(timespec="seconds"), a.qid + (f":{i}" if a.qid == "Q6" else ""), a.n, a.need,
                       a.status, a.text) for i, a in enumerate(out)])
    conn.commit()


def weekly_lines(conn, bars: dict, config, now: datetime, book=None, intents: Optional[dict] = None,
                 save: bool = True) -> list[Line]:
    """The Saturday section. Never raises: a problem shows as one line. A dry run (save=False) stores nothing."""
    try:
        today = now.astimezone(NY).date()
        exps = tuple(e.id for e in config.experiments if e.enabled)
        out = answers(conn, bars, config, today, now, book, intents, exps)
        if save:
            store(conn, out, now)
        return [a.line() for a in out]
    except Exception as exc:
        return [Line(f"Learning questions could not be scored this week ({type(exc).__name__}: {exc}).", SRC, "down")]
