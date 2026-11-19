"""Deterministic risk math: position size, drawdown pause, deposit split, ranking. No AI here."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Literal, Optional

from tradeagent import market_calendar
from tradeagent.config import Profile

Bucket = Literal["long_term", "short_term"]


@dataclass(frozen=True)
class Sizing:
    size_usd: float
    max_loss_usd: float
    limited_by: Literal["risk", "position_cap", "bucket_room", "cash", "none"]


def bucket_room(profile: Profile, bucket: Bucket, account_value: float, bucket_value: float) -> float:
    """Dollars that can still go into ``bucket`` before it passes the top of its band."""
    band = getattr(profile.buckets, bucket)
    return max(0.0, band.max * account_value - bucket_value)


def size_position(
    *,
    profile: Profile,
    tier: int,
    account_value: float,
    entry: float,
    stop: Optional[float],
    room_usd: float,
    cash_usd: float,
    position_cap_pct: float,
) -> Sizing:
    """Largest dollar position that satisfies every limit at once:
    loss at the stop within the profile's cap, at most ``position_cap_pct`` of the account,
    and no more than the bucket's room or the cash available.

    Long-term buys (no stop) are sized by the position cap, bucket room and cash.
    """
    if account_value <= 0 or entry <= 0:
        raise ValueError("account_value and entry must be positive")
    if tier not in (1, 2, 3):
        raise ValueError("tier must be 1, 2 or 3")
    if not 0 < position_cap_pct <= 1:
        raise ValueError("position_cap_pct must be in (0, 1]")
    candidates: list[tuple[float, str]] = [
        (position_cap_pct * account_value, "position_cap"), (room_usd, "bucket_room"), (cash_usd, "cash"),
    ]
    stop_frac = None
    if stop is not None:
        if stop >= entry:
            raise ValueError("stop must be below entry")
        stop_frac = (entry - stop) / entry
        cap = profile.tier3_max_loss_per_trade if tier == 3 else profile.max_loss_per_trade
        candidates.append((cap * account_value / stop_frac, "risk"))
    size, limited_by = min(candidates, key=lambda x: x[0])
    size = max(0.0, size)
    max_loss = size * stop_frac if stop_frac is not None else size
    return Sizing(round(size, 2), round(max_loss, 2), limited_by if size > 0 else "none")


def planned_exit_day(entry_day: date, max_hold_days: int) -> date:
    """The last trading session a trade may be held, counting the entry day as day 1."""
    if max_hold_days < 1:
        raise ValueError("max_hold_days must be >= 1")
    session = market_calendar.session(entry_day)
    day = entry_day if session else market_calendar.next_session(entry_day).day
    for _ in range(max_hold_days - 1):
        day = market_calendar.next_session(day).day
    return day


def earnings_blocks_entry(
    *,
    enabled: bool,
    is_etf: bool,
    entry_day: date,
    max_hold_days: int,
    next_earnings: Optional[date],
) -> tuple[bool, str]:
    """Block a new short-term stock entry if earnings could land before the planned exit.

    Fails closed: a stock with no known earnings date is blocked, because a gap can't be ruled out.
    ETFs don't report earnings and are never blocked.
    """
    if not enabled or is_etf:
        return False, ""
    if next_earnings is None:
        return True, "next earnings date unknown"
    exit_day = planned_exit_day(entry_day, max_hold_days)
    if entry_day <= next_earnings <= exit_day:
        return True, f"earnings {next_earnings:%b %d} before planned exit {exit_day:%b %d}"
    return False, ""


def drawdown_paused(account_value: float, peak_value: float, profile: Profile) -> bool:
    """True when the account is at least ``drawdown_pause`` below its peak: no new short-term trades."""
    if peak_value <= 0:
        return False
    return account_value <= peak_value * (1 - profile.drawdown_pause) + 1e-9


def split_deposit(amount: float, long_term_value: float, short_term_value: float, profile: Profile) -> dict[str, float]:
    """Fill the bucket that is furthest below target first; if both are below, this lands both on target."""
    if amount < 0:
        raise ValueError("amount must be >= 0")
    total = long_term_value + short_term_value + amount
    want_lt = profile.buckets.long_term.target * total - long_term_value
    to_lt = min(max(want_lt, 0.0), amount)
    return {"long_term": round(to_lt, 2), "short_term": round(amount - to_lt, 2)}


@dataclass(frozen=True)
class Idea:
    symbol: str
    setup_id: str
    tier: int
    stars: int
    expected_return: float


def rank(ideas: list[Idea], profile: Profile) -> list[Idea]:
    """Aggressive: highest expected return first. Moderate: most stars first, then expected return."""
    if profile.rank_by == "expected_return":
        return sorted(ideas, key=lambda i: (-i.expected_return, -i.stars, i.symbol))
    return sorted(ideas, key=lambda i: (-i.stars, -i.expected_return, i.symbol))
