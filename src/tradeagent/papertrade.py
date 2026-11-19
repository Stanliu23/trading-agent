"""Hypothetical portfolio: what the account would look like if every recommendation had been followed.

Used twice: to replay recent history now, and as the shadow run's pretend account (no real money).
Daily bars only. Order of events each session:
  1. deposit (first session of a month, after the start day), split between buckets;
  2. at the open: fill exits decided last close, then entries decided last close;
  3. during the day: stops and targets (stop first if both are touched; gaps fill at the open);
  4. at the close: time exits, exit signals (filled next open), account value, profile latch;
  5. at the close: rank today's setup signals, size them, queue entries for the next open.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd

from tradeagent import risk
from tradeagent.config import Config, active_profile
from tradeagent.setups import indicators as ind
from tradeagent.setups.library import CORE_ETFS, ETFS, LIBRARY, Setup
from tradeagent.triggers import bucket_drift

MIN_ORDER_USD = 1.0  # Schwab fractional orders start at $1


@dataclass
class Position:
    symbol: str
    setup_id: str
    bucket: str
    qty: float
    entry: float
    stop: Optional[float]
    target: Optional[float]
    entry_day: pd.Timestamp
    max_hold: Optional[int]
    sessions_held: int = 0
    pending_exit: bool = False


@dataclass
class ClosedTrade:
    symbol: str
    setup_id: str
    bucket: str
    entry_day: pd.Timestamp
    exit_day: pd.Timestamp
    entry: float
    exit: float
    dollars_in: float
    pnl: float
    reason: str


@dataclass
class SimResult:
    daily: pd.DataFrame                      # value, cash_lt, cash_st, lt_value, st_value, positions, profile
    trades: list[ClosedTrade]
    open_positions: list[Position]
    blocked: Counter                         # signals not taken, by reason
    signals_seen: int
    alerts: Counter                          # urgent/digest alert counts by rule
    deposits: list[tuple[pd.Timestamp, float, dict]]
    notes: list[str] = field(default_factory=list)


def _stops(setup: Setup, df: pd.DataFrame, i: int, entry_est: float) -> tuple[Optional[float], Optional[float]]:
    """Stop and target for a signal at bar i, using the same rules as the backtest."""
    if setup.stop_from_signal_low:
        stop = float(df["low"].iloc[i])
    else:
        a = ind.atr(df.iloc[: i + 1], 14).iloc[-1]
        if not np.isfinite(a):
            return None, None
        stop = entry_est - setup.stop_atr * a
    risk_per_share = entry_est - stop
    if setup.target_r is not None:
        target = entry_est + setup.target_r * risk_per_share
    elif setup.target_atr is not None:
        a = ind.atr(df.iloc[: i + 1], 14).iloc[-1]
        target = entry_est + setup.target_atr * a
    else:
        target = None
    return stop, target


def simulate_portfolio(
    bars: dict[str, pd.DataFrame],
    config: Config,
    stats: dict[str, dict],
    start: str,
    end: str,
    starting_cash: float,
    monthly_deposit: float,
    earnings: dict[str, list] | None = None,
) -> SimResult:
    """Run the hypothetical account from ``start`` to ``end``. ``stats`` maps setup id -> stats dict."""
    earnings = earnings or {}
    cost_half = config.backtest.round_trip_cost / 2
    calendar = bars["SPY"].loc[start:end].index
    swing = [s for s in LIBRARY if s.kind == "swing" and stats.get(s.id, {}).get("passes_evidence")]
    # Precompute signals, exit signals once per symbol.
    sig, exs = {}, {}
    for s in swing:
        for sym in s.universe:
            df = bars.get(sym)
            if df is None:
                continue
            sig[(s.id, sym)] = s.signal(df).fillna(False).astype(bool)
            if s.exit_signal:
                exs[(s.id, sym)] = s.exit_signal(df).fillna(False).astype(bool)

    cash = {"long_term": 0.0, "short_term": 0.0}
    positions: list[Position] = []
    trades: list[ClosedTrade] = []
    queued: list[tuple[Setup, str, float, Optional[float], Optional[float], str]] = []  # setup, sym, dollars, stop, target, bucket
    blocked, alerts = Counter(), Counter()
    deposits, rows = [], []
    signals_seen = 0
    ever_reached = False
    peak = 0.0
    paused = False
    lt_rotation = 0
    drifting: dict[str, bool] = {}

    def price(sym, day, col="close"):
        df = bars[sym]
        return float(df.at[day, col]) if day in df.index else None

    def deposit(amount, day):
        lt_val = sum(p.qty * (price(p.symbol, day, "open") or p.entry) for p in positions if p.bucket == "long_term")
        st_val = sum(p.qty * (price(p.symbol, day, "open") or p.entry) for p in positions if p.bucket == "short_term")
        profile = active_profile(config, ever_reached_switch=ever_reached)
        split = risk.split_deposit(amount, lt_val + cash["long_term"], st_val + cash["short_term"], profile)
        cash["long_term"] += split["long_term"]
        cash["short_term"] += split["short_term"]
        deposits.append((day, amount, split))

    def close_position(p: Position, px: float, day, reason: str):
        proceeds = p.qty * px * (1 - cost_half)
        cash[p.bucket] += proceeds
        dollars_in = p.qty * p.entry
        trades.append(ClosedTrade(p.symbol, p.setup_id, p.bucket, p.entry_day, day, p.entry, px,
                                  round(dollars_in, 2), round(proceeds - dollars_in * (1 + cost_half), 2), reason))
        positions.remove(p)
        if reason in ("stop", "target"):
            alerts[f"urgent:{reason}"] += 1

    for n, day in enumerate(calendar):
        month_start = n == 0 or calendar[n - 1].month != day.month
        if n == 0:
            deposit(starting_cash, day)
        elif month_start:
            deposit(monthly_deposit, day)

        # 2. open: exits then entries
        for p in [p for p in positions if p.pending_exit]:
            close_position(p, price(p.symbol, day, "open"), day, "signal")
        for setup, sym, dollars, stop, target, bucket in queued:
            o = price(sym, day, "open")
            if o is None:
                continue
            if stop is not None and o <= stop:
                blocked["gapped below stop before entry"] += 1
                cash[bucket] += dollars
                continue
            qty = dollars * (1 - cost_half) / o
            positions.append(Position(sym, setup.id, bucket, qty, o, stop, target, day, setup.max_hold_days))
        queued = []

        # 3. intraday stops/targets (short-term only)
        for p in list(positions):
            if p.stop is None:
                continue
            o, h, l = price(p.symbol, day, "open"), price(p.symbol, day, "high"), price(p.symbol, day, "low")
            if o is None:
                continue
            first_day = p.entry_day == day
            if not first_day and o <= p.stop:
                close_position(p, o, day, "stop")
            elif l <= p.stop:
                close_position(p, p.stop, day, "stop")
            elif p.target is not None and not first_day and o >= p.target:
                close_position(p, o, day, "target")
            elif p.target is not None and h >= p.target:
                close_position(p, p.target, day, "target")

        # 4. close: hold counters, time exits, exit signals, moves on holdings
        for p in list(positions):
            c = price(p.symbol, day)
            if c is None:
                continue
            p.sessions_held += 1
            df = bars[p.symbol]
            i = df.index.get_loc(day)
            if i >= 61:
                sigma = df["close"].iloc[i - 60:i].pct_change().dropna().std()
                prev = df["close"].iloc[i - 1]
                z_close = abs(c / prev - 1) / sigma if sigma > 0 else 0
                z_intra = max(abs(df["high"].iloc[i] / prev - 1), abs(df["low"].iloc[i] / prev - 1)) / sigma if sigma > 0 else 0
                if z_intra >= config.triggers.urgent_move_sigma:
                    alerts["urgent:3σ move (intraday touch)"] += 1
                elif z_intra >= config.triggers.move_sigma:
                    alerts["digest:2σ move (intraday touch)"] += 1
                if z_close >= config.triggers.urgent_move_sigma:
                    alerts["(close-to-close ≥3σ)"] += 1
            if p.max_hold and p.sessions_held >= p.max_hold:
                close_position(p, c, day, "time")
            elif exs.get((p.setup_id, p.symbol)) is not None and bool(exs[(p.setup_id, p.symbol)].get(day, False)):
                p.pending_exit = True

        lt_val = sum(p.qty * (price(p.symbol, day) or p.entry) for p in positions if p.bucket == "long_term")
        st_val = sum(p.qty * (price(p.symbol, day) or p.entry) for p in positions if p.bucket == "short_term")
        value = lt_val + st_val + cash["long_term"] + cash["short_term"]
        if value >= config.profiles.switch_to_moderate_at:
            ever_reached = True
        profile = active_profile(config, ever_reached_switch=ever_reached)
        if value > peak:
            peak, paused = value, False
        if not paused and risk.drawdown_paused(value, peak, profile):
            paused = True
            alerts["urgent:drawdown pause"] += 1
        if bucket_drift(lt_val + cash["long_term"], st_val + cash["short_term"], profile, day.date(), drifting):
            alerts["digest:bucket drift"] += 1
        rows.append({"date": day, "value": value, "cash_lt": cash["long_term"], "cash_st": cash["short_term"],
                     "lt_value": lt_val, "st_value": st_val, "positions": len(positions),
                     "profile": "moderate" if ever_reached else "aggressive", "paused": paused})

        # 5a. long-term: spend long-term cash on the core ETF we hold least of (equal spread)
        if cash["long_term"] >= MIN_ORDER_USD and n + 1 < len(calendar):
            held = Counter({p.symbol: p.qty * (price(p.symbol, day) or p.entry) for p in positions if p.bucket == "long_term"})
            sym = min(CORE_ETFS, key=lambda s: (held.get(s, 0), (CORE_ETFS.index(s) - lt_rotation) % len(CORE_ETFS)))
            lt_rotation += 1
            room = risk.bucket_room(profile, "long_term", value, lt_val)
            cap_left = config.positions.max_position_pct - held.get(sym, 0) / value
            if cap_left <= 0:
                blocked["long-term cash idle (every core ETF at the 25% cap)"] += 1
                sz = None
            else:
                sz = risk.size_position(profile=profile, tier=stats["L1"].get("tier") or 3, account_value=value,
                                        entry=price(sym, day), stop=None, room_usd=room, cash_usd=cash["long_term"],
                                        position_cap_pct=cap_left)
            if sz is None:
                pass
            elif sz.size_usd >= MIN_ORDER_USD:
                cash["long_term"] -= sz.size_usd
                queued.append((next(s for s in LIBRARY if s.id == "L1"), sym, sz.size_usd, None, None, "long_term"))
            elif cash["long_term"] >= MIN_ORDER_USD:
                blocked[f"long-term cash idle ({sz.limited_by})"] += 1

        # 5b. short-term signals
        if n + 1 >= len(calendar):
            continue
        held_syms = {p.symbol for p in positions} | {q[1] for q in queued}
        cands = []
        for s in swing:
            for sym in s.universe:
                ser = sig.get((s.id, sym))
                if ser is None or not bool(ser.get(day, False)):
                    continue
                signals_seen += 1
                if sym in held_syms:
                    blocked["already held"] += 1
                    continue
                st = stats[s.id]
                cands.append((s, sym, st))
        if not cands:
            continue
        if paused:
            blocked["drawdown pause"] += len(cands)
            continue
        ideas = [risk.Idea(sym, s.id, st["tier"], 0, st["mean_ret"]) for s, sym, st in cands]
        order = risk.rank(ideas, profile)
        by_key = {(s.id, sym): (s, sym, st) for s, sym, st in cands}
        for idea in order:
            s, sym, st = by_key[(idea.setup_id, idea.symbol)]
            if sym in held_syms:
                blocked["same symbol, lower-ranked setup"] += 1
                continue
            if config.positions.skip_entries_before_earnings and sym not in ETFS:
                next_day = calendar[n + 1].date()
                eds = [d for d in earnings.get(sym, []) if d >= next_day]
                if sym not in earnings:
                    blocked["earnings date unknown"] += 1
                    continue
                if eds:
                    exit_day = risk.planned_exit_day(next_day, s.max_hold_days)
                    if min(eds) <= exit_day:
                        blocked["earnings before planned exit"] += 1
                        continue
            df = bars[sym]
            i = df.index.get_loc(day)
            stop, target = _stops(s, df, i, float(df["close"].iloc[i]))
            if stop is None or stop >= df["close"].iloc[i]:
                blocked["no valid stop"] += 1
                continue
            room = risk.bucket_room(profile, "short_term", value, st_val + sum(q[2] for q in queued if q[5] == "short_term"))
            sz = risk.size_position(profile=profile, tier=st["tier"], account_value=value, entry=float(df["close"].iloc[i]),
                                    stop=stop, room_usd=room, cash_usd=cash["short_term"],
                                    position_cap_pct=config.positions.max_position_pct)
            if sz.size_usd < MIN_ORDER_USD:
                blocked[f"no room ({sz.limited_by})"] += 1
                continue
            cash["short_term"] -= sz.size_usd
            queued.append((s, sym, sz.size_usd, stop, target, "short_term"))
            held_syms.add(sym)
            alerts["digest:new recommendation"] += 1

    daily = pd.DataFrame(rows).set_index("date")
    return SimResult(daily, trades, positions, blocked, signals_seen, alerts, deposits)
