"""Strategy experiments, each in its OWN Alpaca paper account (approved 2026-11-23). No real money anywhere.

Stanley's choices: the whole $1,000 account runs the strategy (0/100), emails are weekly only (a section in the
Saturday report), and his moves are final:
- a stock you sell (any amount) in an experiment account is handed to you: the agent never trades it there again,
  and the next-ranked stock takes its place at the next rebalance;
- shares you buy are yours: the agent never sells them and leaves them out of its 10%-each sizing;
- an agent order you cancel is never sent again.

Monthly cycle (cycle = the calendar month):
1. first run of the month on a trading day (normally 08:00 premarket on the 1st session): rank at the previous
   month's last close, then send the sells (whole positions that left the top 10, and trims above 10%);
2. once every sell has finished at Alpaca (usually the first 15-minute run after the open), send the buys from the
   cash Alpaca actually has, so nothing is bought on margin;
3. the month is done. The first month an experiment runs, step 1 happens on its first run.
Only the agent's own orders carry the "tx-<id>-" order id. Safety: the agent refuses to trade an experiment whose
Alpaca account is the main paper account or another experiment's (keys saved in the wrong slot).
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Callable, Optional

import pandas as pd

from tradeagent import alpaca, db, secrets, strategies
from tradeagent.emailer import Line
from tradeagent.setups.library import TRADED_STOCKS

FINAL = {"filled", "canceled", "expired", "rejected", "replaced", "done_for_day"}
MIN_ORDER = 1.0
MAX_FAILS = 3


def key_names(exp_id: str) -> tuple[str, str]:
    return f"alpaca_exp_{exp_id.lower()}_key", f"alpaca_exp_{exp_id.lower()}_secret"


def ready(exp) -> bool:
    return exp.enabled and all(secrets.has_secret(n) for n in key_names(exp.id))


def client_for(exp_id: str, transport=alpaca.urllib_transport) -> alpaca.Client:
    k, s = key_names(exp_id)
    return alpaca.Client(transport, key_name=k, secret_name=s)


def prefix(exp_id: str) -> str:
    return f"tx-{exp_id.lower()}-"


def cid(exp_id: str, cycle: str, side: str, symbol: str) -> str:
    return f"{prefix(exp_id)}{cycle}-{side}-{symbol}"


# --- the account, rebuilt from Alpaca's orders ---------------------------------------------------------------------

@dataclass
class Book:
    agent_qty: dict[str, float]
    yours: dict[str, float]
    blocked: dict[str, str]                      # symbol -> day you sold it
    cancelled: set[str]                          # agent order ids you cancelled
    pending: set[str]                            # agent order ids not finished yet
    known: set[str]                              # agent order ids Alpaca has
    notes: list[str] = field(default_factory=list)


def book(orders: list[dict], positions: list[dict], exp_id: str) -> Book:
    pre = prefix(exp_id)
    agent, blocked = defaultdict(float), {}
    cancelled, pending, known = set(), set(), set()
    for o in orders:
        c, sym, side = o.get("client_order_id") or "", o["symbol"], o["side"]
        q = float(o.get("filled_qty") or 0)
        if c.startswith(pre):
            known.add(c)
            if o["status"] not in FINAL:
                pending.add(c)
            if o["status"] == "canceled":
                cancelled.add(c)                 # the agent never cancels, so this was you
            if sym not in blocked:
                agent[sym] += q if side == "buy" else -q
        elif side == "sell" and q > 0:
            blocked.setdefault(sym, (o.get("filled_at") or o.get("submitted_at") or "")[:10])
            agent[sym] = 0.0                     # whatever is left of it is yours now
    pos = {p["symbol"]: float(p["qty"]) for p in positions}
    agent_qty = {s: min(q, pos.get(s, 0.0)) for s, q in agent.items() if s not in blocked and min(q, pos.get(s, 0.0)) > 1e-9}
    yours = {s: q - agent_qty.get(s, 0.0) for s, q in pos.items() if q - agent_qty.get(s, 0.0) > 1e-9}
    notes = [f"You sold {s} on {d}: the agent will not trade it in this account again." for s, d in blocked.items()]
    notes += [f"You hold {q:.4f} {s} yourself; the agent leaves it alone." for s, q in yours.items()]
    notes += [f"You cancelled the agent's order {c}; it will not be sent again." for c in sorted(cancelled)]
    return Book(agent_qty, yours, blocked, cancelled, pending, known, notes)


# --- one run --------------------------------------------------------------------------------------------------------

def _meta(conn, key: str) -> Optional[str]:
    return db.get_meta(conn, key)


def _set(conn, key: str, value: str) -> None:
    conn.execute("INSERT INTO meta(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                 (key, value))
    conn.commit()


def _intents(conn, exp_id: str) -> dict[str, dict]:
    return {r["client_order_id"]: dict(r) for r in conn.execute("SELECT * FROM exp_intents WHERE exp_id = ?", (exp_id,))}


def _record(conn, now: datetime, exp_id: str, cycle: str, c: str, symbol: str, side: str, dollars, qty, status, detail):
    conn.execute("INSERT INTO exp_intents(client_order_id, exp_id, cycle, placed_at, symbol, side, dollars, qty, status, "
                 "detail) VALUES (?,?,?,?,?,?,?,?,?,?) ON CONFLICT(client_order_id) DO UPDATE SET status=excluded.status, "
                 "detail=excluded.detail, placed_at=excluded.placed_at",
                 (c, exp_id, cycle, now.isoformat(timespec="seconds"), symbol, side, dollars, qty, status, detail))
    conn.commit()


def start_info(conn, exp_id: str, client, today: Optional[date] = None) -> tuple[str, float]:
    """The day the experiment started and its balance then (recorded once, at its first run)."""
    d, e = _meta(conn, f"exp:{exp_id}:start"), _meta(conn, f"exp:{exp_id}:start_equity")
    if d is None or e is None:
        a = client.account()
        d, e = (today or date.today()).isoformat(), str(round(float(a["equity"]), 2))
        _set(conn, f"exp:{exp_id}:start", d)
        _set(conn, f"exp:{exp_id}:start_equity", e)
    return d, float(e)


def step(exp_id: str, client, c: pd.DataFrame, today: date, conn, now: datetime) -> list[str]:
    """Advance this month's rebalance as far as it can go now. Returns what it did, in plain English."""
    cycle = f"{today:%Y%m}"
    done_key, plan_key = f"exp:{exp_id}:{cycle}:done", f"exp:{exp_id}:{cycle}:plan"
    if _meta(conn, done_key):
        return []
    start, _ = start_info(conn, exp_id, client, today)
    b = book(client.orders(f"{start}T00:00:00Z"), client.positions(), exp_id)
    cash = float(client.account()["cash"])
    px = c.loc[:pd.Timestamp(today) - pd.DateOffset(days=1)].iloc[-1]          # last full close
    intents = _intents(conn, exp_id)
    plan = json.loads(_meta(conn, plan_key) or "null")
    out = []

    if plan is None:
        sig = strategies.signal_day(c.index, today)
        tg = strategies.targets(exp_id, c, sig, set(b.blocked))
        value = cash + sum(q * px[s] for s, q in b.agent_qty.items())
        each = value / strategies.TOP_N
        sells = []
        for s, q in sorted(b.agent_qty.items()):
            have = q * px[s]
            if s not in tg:
                sells.append([s, q])
            elif have - each >= MIN_ORDER:
                sells.append([s, (have - each) / px[s]])
        plan = {"signal": sig.date().isoformat(), "targets": tg, "sells": sells, "buys": None, "fails": {}}
        _set(conn, plan_key, json.dumps(plan))
        out.append(f"Ranked at the {sig:%b %d} close: {', '.join(tg)}.")

    sent_now: set[str] = set()

    def send(side, sym, *, qty=None, dollars=None) -> bool:
        """True once the order is at Alpaca (or given up on)."""
        k = cid(exp_id, cycle, side, sym)
        if k in b.known or intents.get(k, {}).get("status") == "sent":
            return True
        if plan["fails"].get(k, 0) >= MAX_FAILS:
            return True
        try:
            client.market_order(sym, side, k, **({"qty": qty} if qty is not None else {"notional": round(dollars, 2)}))
            _record(conn, now, exp_id, cycle, k, sym, side, dollars, qty, "sent", None)
            sent_now.add(k)
            out.append(f"{'Sold' if side == 'sell' else 'Bought'} {sym} "
                       f"({f'{qty:.4f} shares' if qty is not None else f'${dollars:,.2f}'}), at the next fill.")
            return True
        except alpaca.AlpacaError as exc:
            plan["fails"][k] = plan["fails"].get(k, 0) + 1
            _set(conn, plan_key, json.dumps(plan))
            _record(conn, now, exp_id, cycle, k, sym, side, dollars, qty, "failed", str(exc)[:200])
            out.append(f"Order {k} failed ({exc}); " + ("giving up this month." if plan["fails"][k] >= MAX_FAILS
                                                         else "will retry next run."))
            return plan["fails"][k] >= MAX_FAILS

    sells_out = [send("sell", s, qty=q) for s, q in plan["sells"] if s not in b.blocked]
    if not all(sells_out):
        return out
    def unfinished(k: str) -> bool:
        """Sent but not finished at Alpaca yet (or sent so recently that Alpaca does not list it)."""
        sent = k in sent_now or intents.get(k, {}).get("status") == "sent"
        return k in b.pending or (sent and k not in b.known)

    if any(unfinished(cid(exp_id, cycle, "sell", s)) for s, _ in plan["sells"] if s not in b.blocked):
        return out                                # wait for the sells to finish, then buy from real cash
    if plan["buys"] is None:
        value = cash + sum(q * px[s] for s, q in b.agent_qty.items())
        each = value / strategies.TOP_N
        need = {s: each - b.agent_qty.get(s, 0.0) * px[s] for s in plan["targets"] if s not in b.blocked}
        need = {s: x for s, x in need.items() if x >= MIN_ORDER}
        room = max(cash - MIN_ORDER, 0.0)
        scale = min(1.0, room / sum(need.values())) if need else 1.0
        plan["buys"] = [[s, round(x * scale, 2)] for s, x in need.items() if x * scale >= MIN_ORDER]
        _set(conn, plan_key, json.dumps(plan))
    buys_out = [send("buy", s, dollars=d) for s, d in plan["buys"] if s not in b.blocked]
    if all(buys_out):
        _set(conn, done_key, now.isoformat(timespec="seconds"))
        _set(conn, f"exp:{exp_id}:last_rebalance", today.isoformat())
    return out


def save_close(conn, exp_id: str, client, day: date) -> None:
    a = client.account()
    conn.execute("INSERT INTO exp_daily(exp_id, day, equity, cash) VALUES (?,?,?,?) ON CONFLICT(exp_id, day) DO UPDATE "
                 "SET equity=excluded.equity, cash=excluded.cash", (exp_id, day.isoformat(), float(a["equity"]),
                                                                   float(a["cash"])))
    conn.commit()


def _distinct(clients: dict[str, alpaca.Client], main: Optional[alpaca.Client]) -> dict[str, str]:
    """Experiment id -> why it must not trade (its account is the main one or another experiment's)."""
    numbers = {k: str(c.account().get("account_number")) for k, c in clients.items()}
    main_no = str(main.account().get("account_number")) if main is not None else None
    bad = {}
    for k, n in numbers.items():
        if n == main_no:
            bad[k] = "its keys open the MAIN paper account"
        elif list(numbers.values()).count(n) > 1:
            bad[k] = "its keys open the same account as another experiment"
    return bad


def run_all(config, conn, bars, today: date, now: datetime, kind: str, dry_run: bool,
            main_client: Optional[alpaca.Client] = None,
            make_client: Callable[[str], alpaca.Client] = client_for) -> str:
    """Called by the scheduler on trading days. Never raises; returns a short status for the run log."""
    exps = [e for e in config.experiments if ready(e)]
    if not exps:
        return ""
    parts = []
    try:
        clients = {e.id: make_client(e.id) for e in exps}
        bad = _distinct(clients, main_client)
        c = strategies.closes(bars, list(TRADED_STOCKS))
    except Exception as exc:
        return f"experiments: error ({type(exc).__name__}: {exc}); "
    for e in exps:
        try:
            if e.id in bad:
                _set(conn, f"exp:{e.id}:problem", f"Not trading: {bad[e.id]}. Save this experiment's own keys.")
                parts.append(f"{e.id} blocked ({bad[e.id]})")
                continue
            conn.execute("DELETE FROM meta WHERE key = ?", (f"exp:{e.id}:problem",))
            conn.commit()
            if kind in ("premarket", "intraday") and not dry_run:
                did = step(e.id, clients[e.id], c, today, conn, now)
                if did:
                    _set(conn, f"exp:{e.id}:last_note", f"{today}: " + " ".join(did))
                    parts.append(f"{e.id}: {len(did)} step(s)")
            if kind == "close" and not dry_run:                 # a dry run records no start and no close
                start_info(conn, e.id, clients[e.id], today)
                save_close(conn, e.id, clients[e.id], today)
        except Exception as exc:
            _set(conn, f"exp:{e.id}:problem", f"{today}: {type(exc).__name__}: {exc}"[:300])
            parts.append(f"{e.id} error ({type(exc).__name__})")
    return ("experiments: " + ", ".join(parts) + "; ") if parts else ""


# --- the Saturday section ---------------------------------------------------------------------------------------------

def weekly_lines(config, conn, bars, now: datetime, make_client: Callable[[str], alpaca.Client] = client_for,
                 main_since: Optional[Callable[[str], Optional[float]]] = None) -> list[Line]:
    out: list[Line] = []
    exps = [e for e in config.experiments if e.enabled]
    if not exps:
        return out
    spy = bars["SPY"]["close"]
    for e in exps:
        name = f"{strategies.NAMES[e.id]} experiment"
        src = f"Alpaca experiment {e.id}"
        if not ready(e):
            out.append(Line(f"{name}: not started (its Alpaca keys are not saved).", None))
            continue
        problem = _meta(conn, f"exp:{e.id}:problem")
        if problem:
            out.append(Line(f"{name}: {problem}", src, "down"))
        rows = conn.execute("SELECT day, equity FROM exp_daily WHERE exp_id = ? ORDER BY day", (e.id,)).fetchall()
        start, start_eq = _meta(conn, f"exp:{e.id}:start"), _meta(conn, f"exp:{e.id}:start_equity")
        if not rows or start is None:
            out.append(Line(f"{name}: no closing value saved yet.", src))
            continue
        eq = rows[-1][1]
        since = eq / float(start_eq) - 1
        s0 = spy.loc[:pd.Timestamp(start) - pd.DateOffset(days=1)]
        spy_since = float(spy.iloc[-1] / s0.iloc[-1] - 1) if len(s0) else None
        wk = [r for r in rows if pd.Timestamp(r[0]) < pd.Timestamp(now.date()) - pd.DateOffset(days=6)]
        week = eq / wk[-1][1] - 1 if wk else None
        text = (f"{name} (own paper account, whole account in the strategy): ${eq:,.2f}, {since:+.1%} since {start}"
                + (f" (SPY {spy_since:+.1%})" if spy_since is not None else "")
                + (f"; this week {week:+.1%}" if week is not None else "") + ".")
        if main_since is not None and (m := main_since(start)) is not None:
            text = text[:-1] + f"; main paper account {m:+.1%} over the same days."
        out.append(Line(text, src, "up" if since >= 0 else "down"))
        try:
            client = make_client(e.id)
            b = book(client.orders(f"{start}T00:00:00Z"), client.positions(), e.id)
            held = ", ".join(sorted(b.agent_qty)) or "nothing yet"
            last = _meta(conn, f"exp:{e.id}:last_rebalance")
            out.append(Line(f"{name} holds {len(b.agent_qty)}: {held}" + (f"; last rebalance {last}." if last else "."),
                            src))
            out += [Line(f"{name}: {n}", src) for n in b.notes]
        except Exception as exc:
            out.append(Line(f"{name}: could not read the account ({type(exc).__name__}).", src, "down"))
    out.append(Line("Both experiments FAILED the pass bar and were tested on today's large companies (results look "
                    "better than they were). They are for watching only.", "strategy tournament 2026-11-23"))
    return out
