"""Big-dip D2 as a labelled paper experiment, in a slice of an experiment account (Stanley, 2026-11-23: a 25% slice of
the low-volatility account). D2 FAILED its account test (docs/REPLAY_FINDINGS.md); this is for watching only.

Rules exactly as tested (``library.DIP_D2``):
- signal at a close: a stock's first close 30%+ below its highest close of the last 60 sessions (77 traded stocks);
  several at once: the deepest fall first; skipped if earnings fall before the planned exit or are unknown (as tested);
- buy at the next open (08:00 premarket order) with the slice (25% of the account), one dip at a time;
- stop 2.5 x ATR(14) at the signal close below the fill: the 15-minute checks sell at market at or below it;
- after the first close at or above fill x 1.03: sell at the next open (08:00 premarket order);
- after 20 sessions: sell in the last 20 minutes of the 20th session;
- the per-setup switch: no new buys while D2's last 20 paper trades (every signal, all 77 stocks) average below 0R.
Its orders carry "tx-dip-", so the low-volatility book never mistakes them for yours, and its results are kept apart.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Callable, Optional
from zoneinfo import ZoneInfo

import pandas as pd

from tradeagent import alpaca, db, market_calendar
from tradeagent.setups import indicators as ind
from tradeagent.setups.library import DIP_D2

NY = ZoneInfo("America/New_York")
PREFIX = "tx-dip-"
EXP = "DIP"
FINAL = {"filled", "canceled", "expired", "rejected", "replaced", "done_for_day"}


@dataclass
class Lot:
    symbol: str
    qty: float
    fill: float
    fill_day: date
    buy_cid: str


def _ny_day(ts: str) -> date:
    return datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(NY).date()


def state(orders: list[dict]) -> tuple[Optional[Lot], list[dict], set[str], set[str]]:
    """(open lot, closed trades, unfinished order ids, known order ids) from the account's tx-dip- orders."""
    mine = sorted([o for o in orders if (o.get("client_order_id") or "").startswith(PREFIX)],
                  key=lambda o: o.get("filled_at") or o.get("submitted_at") or "")
    lot, closed, pending, known = None, [], set(), set()
    for o in mine:
        c = o["client_order_id"]
        known.add(c)
        if o["status"] not in FINAL:
            pending.add(c)
        q = float(o.get("filled_qty") or 0)
        if q <= 0 or not o.get("filled_avg_price"):
            continue
        px, day = float(o["filled_avg_price"]), _ny_day(o.get("filled_at") or o["submitted_at"])
        if o["side"] == "buy":
            lot = Lot(o["symbol"], q, px, day, c) if lot is None else Lot(lot.symbol, lot.qty + q, lot.fill, lot.fill_day, lot.buy_cid)
        elif lot is not None and o["symbol"] == lot.symbol:
            closed.append({"symbol": lot.symbol, "buy": lot.fill, "sell": px, "qty": q, "day": day.isoformat(),
                           "why": c.split("-")[3] if c.count("-") >= 4 else "sell", "pnl": q * (px - lot.fill)})
            left = lot.qty - q
            lot = None if left <= 1e-9 else Lot(lot.symbol, left, lot.fill, lot.fill_day, lot.buy_cid)
    return lot, closed, pending, known


def switch_on(bars: dict, cost: float, n: int = 20, min_r: float = 0.0) -> tuple[bool, Optional[float]]:
    """The per-setup switch on D2's paper record (every signal, all 77 stocks, its own exits)."""
    from tradeagent.setups.simulate import simulate_swing
    rows = [(t.exit_date, t.r) for s in DIP_D2.universe if s in bars
            for t in simulate_swing(bars[s], DIP_D2, s, cost) if t.reason != "end" and t.r is not None]
    if len(rows) < n:
        return True, None
    last = [r for _, r in sorted(rows)[-n:]]
    avg = sum(last) / n
    return avg >= min_r, avg


def candidates(bars: dict, day: pd.Timestamp) -> list[tuple[str, float, float, float]]:
    """(symbol, close / 60-day high, ATR(14), close) for every D2 signal at ``day``'s close, deepest first."""
    out = []
    for s in DIP_D2.universe:
        df = bars.get(s)
        if df is None or day not in df.index:
            continue
        d = df.loc[:day]
        if not bool(DIP_D2.signal(d).fillna(False).iloc[-1]):
            continue
        c = float(d["close"].iloc[-1])
        out.append((s, c / float(d["close"].iloc[-60:].max()), float(ind.atr(d, 14).iloc[-1]), c))
    return sorted(out, key=lambda x: x[1])


def _earnings_ok(sym: str, earnings: dict, first: date) -> bool:
    if sym not in earnings:
        return False                                       # unknown: skipped, as in the test
    exit_day = first
    for _ in range(DIP_D2.max_hold_days - 1):
        exit_day = market_calendar.next_session(exit_day).day
    return not any(first <= d <= exit_day for d in earnings[sym])


def _sessions_held(fill_day: date, today: date) -> int:
    n, d = 0, fill_day
    while d <= today:
        if market_calendar.session(d):
            n += 1
        d += timedelta(days=1)
    return n


def _intents(conn) -> dict[str, dict]:
    return {r["client_order_id"]: dict(r) for r in conn.execute("SELECT * FROM exp_intents WHERE exp_id = ?", (EXP,))}


def _record(conn, now, k, sym, side, dollars, qty, status, detail):
    conn.execute("INSERT INTO exp_intents(client_order_id, exp_id, cycle, placed_at, symbol, side, dollars, qty, status, "
                 "detail) VALUES (?,?,?,?,?,?,?,?,?,?) ON CONFLICT(client_order_id) DO UPDATE SET status=excluded.status, "
                 "detail=excluded.detail, placed_at=excluded.placed_at",
                 (k, EXP, f"{now:%Y%m}", now.isoformat(timespec="seconds"), sym, side, dollars, qty, status, detail))
    conn.commit()


def step(conn, client, bars: dict, today: date, now: datetime, kind: str, slice_share: float, earnings: dict,
         cost: float, start: str, quote: Optional[Callable] = None) -> list[str]:
    """One run of the dip slice. Places at most one order. Returns what it did."""
    from tradeagent import market
    quote = quote or market.quote
    orders = client.orders(f"{start}T00:00:00Z")
    lot, _, pending, known = state(orders)
    intents = _intents(conn)
    if pending or any(v["status"] == "sent" and k not in known for k, v in intents.items()):
        return []                                          # an order is still on its way: wait
    out = []

    def send(purpose, sym, *, qty=None, dollars=None, detail=None):
        k = f"{PREFIX}{today:%Y%m%d}-{purpose}-{sym}"
        if k in known or intents.get(k, {}).get("status") in ("sent", "failed"):
            return
        try:
            client.market_order(sym, "buy" if purpose == "buy" else "sell", k,
                                **({"qty": qty} if qty is not None else {"notional": round(dollars, 2)}))
            _record(conn, now, k, sym, "buy" if purpose == "buy" else "sell", dollars, qty, "sent", detail)
            out.append(f"Dip slice: {purpose} {sym}" + (f" ${dollars:,.2f}." if dollars else f" {qty:.4f} shares."))
        except alpaca.AlpacaError as exc:
            _record(conn, now, k, sym, "buy" if purpose == "buy" else "sell", dollars, qty, "failed", str(exc)[:200])
            out.append(f"Dip slice: {purpose} {sym} failed ({exc}).")

    if kind == "premarket":
        flag = db.get_meta(conn, "dip:profit_exit")
        if lot is not None and flag == lot.buy_cid:
            send("profit", lot.symbol, qty=lot.qty, detail=json.dumps({"lot_ref": lot.buy_cid}))
        elif lot is None:
            on, avg = switch_on(bars, cost)
            if not on:
                return [f"Dip slice: switched off by its paper record (last 20 average {avg:+.2f}R)."]
            prev = [d for d in bars["SPY"].index if d.date() < today]
            if not prev:
                return out
            for sym, depth, atr, close in candidates(bars, prev[-1]):
                if not _earnings_ok(sym, earnings, today):
                    continue
                acct = client.account()
                size = min(slice_share * float(acct["equity"]), float(acct["cash"]) - 1.0)
                if size >= 1.0:
                    send("buy", sym, dollars=size, detail=json.dumps({"atr": atr, "signal_close": close,
                                                                      "depth": round(depth, 4)}))
                break
    elif kind == "intraday" and lot is not None:
        buy = intents.get(lot.buy_cid, {})
        atr = json.loads(buy.get("detail") or "{}").get("atr")
        stop = lot.fill - DIP_D2.stop_atr * atr if atr else None
        q = quote(lot.symbol)
        sess = market_calendar.session(today)
        late = sess is not None and now.astimezone(NY) >= sess.close - timedelta(minutes=20)
        if stop is not None and q is not None and q.price <= stop:
            send("stop", lot.symbol, qty=lot.qty, detail=json.dumps({"lot_ref": lot.buy_cid, "stop": stop, "entry": lot.fill}))
        elif late and _sessions_held(lot.fill_day, today) >= DIP_D2.max_hold_days:
            send("time", lot.symbol, qty=lot.qty, detail=json.dumps({"lot_ref": lot.buy_cid}))
    elif kind == "close" and lot is not None:
        df = bars.get(lot.symbol)
        day = pd.Timestamp(today)
        if df is not None and day in df.index and float(df.at[day, "close"]) >= lot.fill * (1 + DIP_D2.profit_close_pct):
            conn.execute("INSERT INTO meta(key, value) VALUES ('dip:profit_exit', ?) ON CONFLICT(key) DO UPDATE SET "
                         "value = excluded.value", (lot.buy_cid,))
            conn.commit()
            out.append(f"Dip slice: {lot.symbol} closed 3%+ above the buy price; selling at the next open.")
    return out


def fill_intents(conn) -> dict[str, dict]:
    """For the fill tracker: order id -> purpose (entry/stop/profit/time), lot and stop."""
    out = {}
    for k, v in _intents(conn).items():
        d = json.loads(v.get("detail") or "{}") if (v.get("detail") or "").startswith("{") else {}
        purpose = k.split("-")[3] if k.count("-") >= 4 else "entry"
        out[k] = {"purpose": "entry" if purpose == "buy" else purpose, "lot_ref": d.get("lot_ref"), "stop": d.get("stop")}
    for k, v in list(out.items()):                       # the stop question needs the lot's stop on the entry intent
        if v["purpose"] == "stop" and v.get("lot_ref") in out:
            out[v["lot_ref"]]["stop"] = v["stop"]
    return out


def weekly_line(orders: list[dict], bars: dict, cost: float) -> str:
    lot, closed, _, _ = state(orders)
    pnl = sum(c["pnl"] for c in closed)
    wins = sum(c["pnl"] > 0 for c in closed)
    on, avg = switch_on(bars, cost)
    held = (f"holding {lot.symbol} bought at ${lot.fill:,.2f} on {lot.fill_day}" if lot else "no dip held")
    return (f"Big-dip D2 slice (25% of this account; failed its test, for watching only): {held}; {len(closed)} closed "
            f"trade(s), {wins} won, together ${pnl:+,.2f}; switch {'on' if on else 'off'}"
            + (f" (last 20 paper trades {avg:+.2f}R)." if avg is not None else "."))
