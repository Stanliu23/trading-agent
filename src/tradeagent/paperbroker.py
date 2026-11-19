"""The 2-week test on Alpaca's paper account: the agent places the shadow plan's trades, you may step in.

How it works:
- The shadow account (``account.build``) still decides: which buys, at what size, with which stop/target.
- ``act`` turns those decisions into Alpaca paper orders, records each one as an intent (why it was placed),
  and watches stops, targets, exit signals and time limits on what the agent bought.
- ``book`` rebuilds the paper account from Alpaca's order history every run: the agent's fills become lots
  with their rules; YOUR orders are respected as final:
    * an agent order you cancel is never re-sent;
    * a sell you place closes lots of that symbol (oldest first) and the agent never buys them back;
    * a buy you place becomes your lot: untagged until you run `tradeagent tag SYMBOL BUCKET`; a short-term
      tag gives it S2's exits (stop 2×ATR below your fill, target 4×ATR above, 20 sessions), long-term is held.
- Money is a virtual budget: the shadow's $300 start and monthly deposits (Alpaca paper can't receive
  deposits), minus buys plus sells by bucket. Alpaca's own paper cash is ignored.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from datetime import date, datetime, timedelta
from typing import Callable, Optional
from zoneinfo import ZoneInfo

import pandas as pd

from tradeagent import market_calendar
from tradeagent.account import AccountState
from tradeagent.config import Config
from tradeagent.papertrade import ClosedTrade, Position, SimResult
from tradeagent.setups import indicators as ind
from tradeagent.setups.library import get

NY = ZoneInfo("America/New_York")
EPS = 1e-6
YOUR_EXITS = "S2"                      # exits given to a short-term buy you make yourself
PREFIX = "ta-"                         # every agent order id starts with this; anything else is yours


@dataclass
class Lot:
    ref: str                           # client_order_id of the buy (agent) or Alpaca order id (yours)
    symbol: str
    setup_id: str                      # "YOU" for your own buys
    bucket: Optional[str]              # None: your buy, not tagged yet
    qty: float
    entry: float
    entry_day: date
    stop: Optional[float] = None
    target: Optional[float] = None
    max_hold: Optional[int] = None
    origin: str = "agent"              # agent | you
    cost: float = 0.0                  # dollars paid for the remaining shares


@dataclass
class Closed:
    lot: Lot
    qty: float
    exit: float
    exit_day: date
    reason: str                        # stop | target | signal | time | you


@dataclass
class Book:
    lots: list[Lot] = field(default_factory=list)
    closed: list[Closed] = field(default_factory=list)
    cash: dict = field(default_factory=lambda: {"long_term": 0.0, "short_term": 0.0})
    pending: list[dict] = field(default_factory=list)      # agent orders not yet filled
    notes: list[tuple[date, str]] = field(default_factory=list)   # (day, what you changed / rejections)
    yours_cancelled: set = field(default_factory=set)       # agent order ids you cancelled

    def held(self) -> set[str]:
        return {l.symbol for l in self.lots}

    def value(self, prices: dict[str, float]) -> tuple[float, float, float]:
        lt = sum(l.qty * prices.get(l.symbol, l.entry) for l in self.lots if l.bucket == "long_term")
        st = sum(l.qty * prices.get(l.symbol, l.entry) for l in self.lots if l.bucket != "long_term")
        return lt + st + self.cash["long_term"] + self.cash["short_term"], lt, st


def _ny_day(ts: str) -> date:
    return datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(NY).date()


def _your_exits(lot: Lot, bars: Optional[dict]) -> Lot:
    if lot.bucket != "short_term" or bars is None or lot.symbol not in bars:
        return lot
    s = get(YOUR_EXITS)
    df = bars[lot.symbol].loc[:pd.Timestamp(lot.entry_day)]
    a = ind.atr(df, 14).iloc[-1] if len(df) > 15 else float("nan")
    if not math.isfinite(a):
        return lot
    return replace(lot, stop=lot.entry - s.stop_atr * a, target=lot.entry + s.target_atr * a, max_hold=s.max_hold_days)


def book(orders: list[dict], intents: dict[str, dict], deposits: list[tuple], tags: dict[str, str],
         bars: Optional[dict] = None) -> Book:
    """Rebuild the paper account from Alpaca's orders (oldest first) and the agent's recorded intents."""
    b = Book()
    for _, _, split in deposits:
        b.cash["long_term"] += split["long_term"]
        b.cash["short_term"] += split["short_term"]
    fills = []
    for o in orders:
        cid, mine = o.get("client_order_id") or "", (o.get("client_order_id") or "").startswith(PREFIX)
        filled = float(o.get("filled_qty") or 0)
        if filled > EPS and o.get("filled_avg_price"):
            fills.append(o)
        if mine and filled <= EPS:
            st = o.get("status")
            when = _ny_day(o.get("canceled_at") or o.get("updated_at") or o.get("submitted_at") or "1970-01-01T00:00:00Z")
            if st == "canceled":
                b.yours_cancelled.add(cid)
                b.notes.append((when, f"You cancelled the agent's {o['side']} of {o['symbol']}; it will not be re-sent."))
            elif st in ("rejected", "expired"):
                b.notes.append((when, f"Alpaca {st} the agent's {o['side']} of {o['symbol']}."))
            elif st not in ("filled",):
                b.pending.append({"cid": cid, "symbol": o["symbol"], "side": o["side"], "intent": intents.get(cid, {})})
    for o in sorted(fills, key=lambda o: o.get("filled_at") or o.get("submitted_at") or ""):
        cid = o.get("client_order_id") or ""
        qty, px, day = float(o["filled_qty"]), float(o["filled_avg_price"]), _ny_day(o.get("filled_at") or o["submitted_at"])
        it = intents.get(cid)
        if o["side"] == "buy":
            if it and cid.startswith(PREFIX):
                lot = Lot(cid, o["symbol"], it["setup_id"], it["bucket"], qty, px, day, it.get("stop"), it.get("target"),
                          it.get("max_hold"), "agent", qty * px)
            else:
                lot = _your_exits(Lot(o.get("id", cid), o["symbol"], "YOU", tags.get(o["symbol"]), qty, px, day,
                                      origin="you", cost=qty * px), bars)
                b.notes.append((day, f"You bought {qty:g} {o['symbol']} at ${px:,.2f}"
                                + ("." if lot.bucket else f": untagged (run `tradeagent tag {o['symbol']} long_term|short_term`).")))
            b.cash[lot.bucket or "short_term"] -= qty * px
            b.lots.append(lot)
            continue
        # sells: the agent's close the lot they name; yours close lots of that symbol, oldest first
        targets = ([l for l in b.lots if l.ref == it.get("lot_ref")] if it and cid.startswith(PREFIX)
                   else [l for l in b.lots if l.symbol == o["symbol"]])
        reason = it["purpose"] if it and cid.startswith(PREFIX) else "you"
        if reason == "you":
            b.notes.append((day, f"You sold {qty:g} {o['symbol']} at ${px:,.2f}; the agent will not buy it back."))
        left = qty
        for lot in targets:
            if left <= EPS:
                break
            take = min(lot.qty, left)
            b.cash[lot.bucket or "short_term"] += take * px
            b.closed.append(Closed(replace(lot, qty=take), take, px, day, reason))
            lot.cost -= lot.cost * take / lot.qty
            lot.qty -= take
            left -= take
        b.lots = [l for l in b.lots if l.qty > EPS]
        if left > EPS:
            b.notes.append((day, f"A sell of {left:g} {o['symbol']} had no matching lot in the agent's book."))
    return b


def check_positions(b: Book, positions: list[dict]) -> list[str]:
    """Alpaca's positions vs the book; a gap means orders the book can't see (e.g. from before the start)."""
    have = {p["symbol"]: float(p["qty"]) for p in positions}
    want: dict[str, float] = {}
    for l in b.lots:
        want[l.symbol] = want.get(l.symbol, 0) + l.qty
    return [f"Alpaca shows {have.get(s, 0):g} {s}, the agent's book {want.get(s, 0):g}."
            for s in sorted(set(have) | set(want)) if abs(have.get(s, 0) - want.get(s, 0)) > 1e-4]


def sessions_held(entry_day: date, today: date) -> int:
    n, d = 0, entry_day
    while d <= today:
        n += market_calendar.session(d) is not None
        d += timedelta(days=1)
    return n


# --- placing orders --------------------------------------------------------------------

@dataclass
class Placed:
    symbol: str
    side: str
    purpose: str
    amount: str                        # "$75.00" or "0.41235 sh"
    ok: bool
    detail: str = ""


def _cid(session: date, purpose: str, symbol: str, extra: str = "") -> str:
    return f"{PREFIX}{session:%Y%m%d}-{purpose}-{symbol}{('-' + extra) if extra else ''}"[:48]


def _send(client, record: Callable[[dict], None], session: date, symbol: str, side: str, purpose: str, *,
          notional=None, qty=None, **intent) -> Placed:
    cid = _cid(session, purpose, symbol, intent.get("setup_id") or "")
    row = {"client_order_id": cid, "session": session.isoformat(), "symbol": symbol, "side": side, "purpose": purpose,
           "dollars": notional, "qty": qty, **intent}
    amount = f"${notional:,.2f}" if notional is not None else f"{qty:.5f} sh"
    try:
        client.market_order(symbol, side, cid, notional=notional, qty=qty)
        record({**row, "status": "sent", "detail": ""})
        return Placed(symbol, side, purpose, amount, True)
    except Exception as exc:                              # rejected at submit: logged, retried later if allowed
        record({**row, "status": "failed", "detail": str(exc)[:300]})
        return Placed(symbol, side, purpose, amount, False, str(exc)[:200])


def place_open(client, b: Book, shadow: AccountState, session: date, intents: dict[str, dict],
               record, config: Config) -> list[Placed]:
    """Exit-signal sells, then the shadow plan's buys, for ``session``. Safe to call repeatedly: each order
    is sent once (a failed send is retried on the next call; one you cancelled never is)."""
    out = []
    pending_syms = {p["symbol"] for p in b.pending}
    sent = {cid for cid, it in intents.items() if it.get("status") == "sent"}
    # 1. exit signals seen at the last close, on what the agent bought
    for lot in list(b.lots):
        s = get(lot.setup_id) if lot.origin == "agent" else None
        if not s or not s.exit_signal or lot.symbol in pending_syms or lot.symbol not in shadow.bars:
            continue
        sig = s.exit_signal(shadow.bars[lot.symbol])
        if len(sig) and bool(sig.iloc[-1]) and lot.entry_day < session:
            cid = _cid(session, "signal", lot.symbol, lot.setup_id)
            if cid not in sent and cid not in b.yours_cancelled:
                out.append(_send(client, record, session, lot.symbol, "sell", "signal", qty=lot.qty,
                                 setup_id=lot.setup_id, bucket=lot.bucket, lot_ref=lot.ref))
    # 2. buys planned at the last close
    min_order = max(1.0, config.positions.min_position_usd)
    held = b.held() | pending_syms
    room = dict(b.cash)
    for p in b.pending:
        if p["side"] == "buy" and p["intent"].get("dollars"):
            room[p["intent"].get("bucket") or "short_term"] -= p["intent"]["dollars"]
    for o in shadow.sim.next_orders:
        cid = _cid(session, "entry", o["symbol"], o["setup_id"])
        if cid in sent or cid in b.yours_cancelled or o["symbol"] in held:
            continue
        dollars = math.floor(min(o["dollars"], room[o["bucket"]]) * 100) / 100
        if dollars < min_order:
            continue
        s = get(o["setup_id"])
        p = _send(client, record, session, o["symbol"], "buy", "entry", notional=dollars, setup_id=o["setup_id"],
                  bucket=o["bucket"], stop=o["stop"], target=o["target"], max_hold=s.max_hold_days)
        if p.ok:
            room[o["bucket"]] -= dollars
            held.add(o["symbol"])
        out.append(p)
    return out


def place_watch(client, b: Book, quotes: dict, session: date, now: datetime, intents: dict[str, dict], record,
                late: bool) -> list[Placed]:
    """Every 15 minutes: stops and targets; in the last 20 minutes, time limits."""
    out = []
    pending_syms = {p["symbol"] for p in b.pending}
    sent = {cid for cid, it in intents.items() if it.get("status") == "sent"}
    for lot in b.lots:
        if lot.symbol in pending_syms or lot.bucket == "long_term":
            continue
        q = quotes.get(lot.symbol)
        purpose = None
        if q is not None and lot.stop is not None and q.price <= lot.stop:
            purpose = "stop"
        elif q is not None and lot.target is not None and q.price >= lot.target:
            purpose = "target"
        elif late and lot.max_hold and sessions_held(lot.entry_day, session) >= lot.max_hold:
            purpose = "time"
        if purpose is None:
            continue
        cid = _cid(session, purpose, lot.symbol, lot.setup_id)
        if cid in sent or cid in b.yours_cancelled:
            continue
        out.append(_send(client, record, session, lot.symbol, "sell", purpose, qty=lot.qty, setup_id=lot.setup_id,
                         bucket=lot.bucket, lot_ref=lot.ref))
        pending_syms.add(lot.symbol)
    return out


def day_events(b: Book, intents: dict[str, dict], day: date) -> list[str]:
    """What happened in the paper account on ``day``, for the digest."""
    out = [f"Bought {l.qty:.5f} {l.symbol} at ${l.entry:,.2f} ({'your buy' if l.origin == 'you' else l.setup_id})."
           for l in b.lots if l.entry_day == day]
    out += [f"Sold {c.qty:.5f} {c.lot.symbol} at ${c.exit:,.2f} ({c.reason}): {c.exit / c.lot.entry - 1:+.1%}."
            for c in b.closed if c.exit_day == day]
    out += [t for d, t in b.notes if d == day]
    out += [f"Not filled yet: the agent's {p['side']} of {p['symbol']}." for p in b.pending]
    out += [f"Alpaca refused the agent's {it['side']} of {it['symbol']}: {it.get('detail', '')}"
            for it in intents.values() if it.get("status") == "failed" and it.get("session") == day.isoformat()]
    return out


# --- the paper account as an AccountState, so every email works unchanged -----------------------

def to_state(shadow: AccountState, b: Book, history: list[dict], day: date, events: tuple = ()) -> AccountState:
    """``history``: stored closes before ``day`` (rows of paper_daily). Today's row is computed from the book."""
    px = {s: float(df["close"].loc[:pd.Timestamp(day)].iloc[-1]) for s, df in shadow.bars.items()
          if len(df.loc[:pd.Timestamp(day)])}
    value, lt, st = b.value(px)
    rows = [r for r in history if r["day"] < day.isoformat()] + [
        {"day": day.isoformat(), "value": value, "cash_lt": b.cash["long_term"], "cash_st": b.cash["short_term"],
         "lt_value": lt, "st_value": st}]
    daily = pd.DataFrame(rows)
    daily.index = pd.to_datetime(daily.pop("day"))
    inflow = {pd.Timestamp(d): a for d, a, _ in shadow.sim.deposits}
    perf, idx, prev = [], 1.0, None
    for d_, v in daily["value"].items():
        if prev:
            idx *= (v - inflow.get(d_, 0.0)) / prev
        perf.append(idx)
        prev = v
    daily["perf_index"] = perf
    daily["profile"] = shadow.sim.daily["profile"].iloc[-1]
    daily["paused"] = shadow.sim.drawdown_paused
    positions = []
    for l in b.lots:
        s = get(l.setup_id) if l.origin == "agent" else None
        pending_exit = bool(s and s.exit_signal and l.symbol in shadow.bars and len(shadow.bars[l.symbol])
                            and bool(s.exit_signal(shadow.bars[l.symbol]).iloc[-1]))
        positions.append(Position(l.symbol, l.setup_id, l.bucket or "short_term", l.qty, l.entry, l.stop, l.target,
                                  pd.Timestamp(l.entry_day), l.max_hold, sessions_held(l.entry_day, day), pending_exit))
    trades = [ClosedTrade(c.lot.symbol, c.lot.setup_id, c.lot.bucket or "short_term", pd.Timestamp(c.lot.entry_day),
                          pd.Timestamp(c.exit_day), c.lot.entry, c.exit, round(c.qty * c.lot.entry, 2),
                          round(c.qty * (c.exit - c.lot.entry), 2), c.reason, c.lot.stop, c.lot.target) for c in b.closed]
    held = b.held()
    room = dict(b.cash)
    nxt = []
    for o in shadow.sim.next_orders:
        if o["symbol"] in held:
            continue
        d = math.floor(min(o["dollars"], room[o["bucket"]]) * 100) / 100
        if d >= 1:
            nxt.append({**o, "dollars": d})
            room[o["bucket"]] -= d
    sim = SimResult(daily, trades, positions, shadow.sim.blocked, shadow.sim.signals_seen, shadow.sim.alerts,
                    shadow.sim.deposits, shadow.sim.notes, shadow.sim.st_inflows, nxt, shadow.sim.goal_paused,
                    shadow.sim.drawdown_paused, shadow.sim.switched_off_now)
    return replace(shadow, sim=sim, label="Alpaca paper", source="Alpaca paper account", paper_events=tuple(events),
                   paper_note="The agent places these in the Alpaca paper account at about 08:00 ET, queued for the "
                              "open. To skip one, cancel it in Alpaca before 09:30; it won't be re-sent.")
