"""Trigger rules: plain code, no AI, no network. Each rule takes data in and returns events out.

An event either wakes the AI immediately (``when="now"``) or waits for the 16:30 close run
(``when="close"``), where one AI run handles every batched event together. ``urgent`` events
are emailed right away; the rest go in the daily digest.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date
from typing import Iterable, Literal, Optional

import numpy as np
import pandas as pd

from tradeagent.config import Config, Profile

When = Literal["now", "close"]


@dataclass(frozen=True)
class Event:
    rule: str
    symbol: Optional[str]
    urgent: bool
    when: When
    key: str                       # dedupe key: the same key fires at most once
    detail: dict = field(default_factory=dict)


# --- price ---------------------------------------------------------------------

def daily_sigma(closes: pd.Series, lookback: int) -> Optional[float]:
    """Std of close-to-close returns over the last ``lookback`` days (ending at the last close given)."""
    rets = closes.pct_change().dropna().tail(lookback)
    if len(rets) < lookback:
        return None
    s = float(rets.std(ddof=1))
    return s if s > 0 and math.isfinite(s) else None


def move(symbol: str, price: float, prev_close: float, sigma: Optional[float], day: date, config: Config) -> Optional[Event]:
    """A move of at least move_sigma × the stock's own daily sigma; urgent at urgent_move_sigma."""
    if sigma is None or prev_close <= 0:
        return None
    ret = price / prev_close - 1
    z = ret / sigma
    t = config.triggers
    if abs(z) < t.move_sigma:
        return None
    urgent = abs(z) >= t.urgent_move_sigma
    level = "urgent" if urgent else "move"
    return Event("move", symbol, urgent, "now", f"move:{level}:{symbol}:{day}",
                 {"return": round(ret, 4), "sigmas": round(z, 2), "price": price, "prev_close": prev_close})


def stop_or_target(symbol: str, price: float, stop: Optional[float], target: Optional[float], day: date) -> Optional[Event]:
    """Stop or target touched by the current price. Long-term positions have neither and never fire."""
    if stop is not None and price <= stop:
        return Event("stop_hit", symbol, True, "now", f"stop:{symbol}:{day}", {"price": price, "stop": stop})
    if target is not None and price >= target:
        return Event("target_hit", symbol, True, "now", f"target:{symbol}:{day}", {"price": price, "target": target})
    return None


# --- account -------------------------------------------------------------------

def bucket_drift(long_term_value: float, short_term_value: float, profile: Profile, day: date,
                 drifting: dict[str, bool]) -> list[Event]:
    """One alert when the split leaves its band. The two buckets always add up to 100%, so long-term
    out of band means short-term is too; checking long-term alone avoids a duplicate alert.
    Fires once per episode: ``drifting`` (updated in place) remembers an episode in progress."""
    total = long_term_value + short_term_value
    if total <= 0:
        return []
    band = profile.buckets.long_term
    share = long_term_value / total
    out_of_band = share < band.min - 1e-9 or share > band.max + 1e-9
    events = []
    if out_of_band and not drifting.get("split", False):
        events.append(Event("bucket_drift", None, False, "close", f"drift:{day}",
                            {"long_term_share": round(share, 4), "long_term_band": [band.min, band.max]}))
    drifting["split"] = out_of_band
    return events


def drawdown(account_value: float, peak_value: float, profile: Profile, already_paused: bool) -> Optional[Event]:
    """Fires once when the account first crosses the pause level; silent while it stays paused."""
    if peak_value <= 0 or already_paused:
        return None
    if account_value <= peak_value * (1 - profile.drawdown_pause) + 1e-9:
        return Event("drawdown_pause", None, True, "now", f"pause:{peak_value:.2f}",
                     {"value": account_value, "peak": peak_value, "pause_at": profile.drawdown_pause})
    return None


def deposits(transactions: Iterable[dict], seen_ids: set[str]) -> list[Event]:
    """New cash deposits. Each transaction: {"id", "date", "type", "amount"}."""
    out = []
    for tx in transactions:
        if tx.get("type") == "deposit" and tx.get("amount", 0) > 0 and str(tx["id"]) not in seen_ids:
            out.append(Event("deposit", None, False, "close", f"deposit:{tx['id']}",
                             {"amount": tx["amount"], "date": str(tx["date"])}))
    return out


# --- calendar, filings, news -----------------------------------------------------

def earnings_soon(symbol: str, next_earnings: Optional[date], sessions_until: Optional[int], config: Config) -> Optional[Event]:
    if next_earnings is None or sessions_until is None:
        return None
    if 0 <= sessions_until <= config.triggers.earnings_within_days:
        return Event("earnings_soon", symbol, False, "close", f"earnings:{symbol}:{next_earnings}",
                     {"date": str(next_earnings), "sessions_until": sessions_until})
    return None


def new_items(rule: Literal["filing", "headline"], symbol: str, items: Iterable[dict], seen_ids: set[str]) -> list[Event]:
    """New filings or headlines (each with a unique "id"). Batched to the close run: the AI checks
    them once a day for measured price impact instead of waking up for every headline."""
    return [Event(rule, symbol, False, "close", f"{rule}:{it['id']}",
                  {k: it.get(k) for k in ("title", "published", "form", "link")})
            for it in items if str(it["id"]) not in seen_ids]


# --- setups (close run) --------------------------------------------------------

def setup_signals(symbol: str, df: pd.DataFrame, setups, held: bool, day: date) -> list[Event]:
    """Setups whose signal is true on the last close. Held symbols are skipped (no doubling up)."""
    if held or df.empty:
        return []
    out = []
    for s in setups:
        if s.kind != "swing":
            continue
        sig = s.signal(df)
        if bool(sig.iloc[-1]) if not pd.isna(sig.iloc[-1]) else False:
            out.append(Event("setup_signal", symbol, False, "close", f"setup:{s.id}:{symbol}:{day}",
                             {"setup": s.id, "close": float(df["close"].iloc[-1])}))
    return out


def dedupe(events: Iterable[Event], fired_keys: set[str]) -> list[Event]:
    out, seen = [], set(fired_keys)
    for e in events:
        if e.key not in seen:
            seen.add(e.key)
            out.append(e)
    return out
