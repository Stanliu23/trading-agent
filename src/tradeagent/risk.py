"""Deterministic risk math: position size, drawdown pause, deposit split, ranking. No AI here."""

from __future__ import annotations

import math
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
    limited_by: Literal["risk", "position_cap", "bucket_room", "cash"]


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
    size = math.floor(size * 100 + 1e-9) / 100  # round down to the cent: never more than the cash available
    max_loss = size * stop_frac if stop_frac is not None else size
    return Sizing(size, round(max_loss, 2), limited_by)  # always names the binding limit


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


def performance_index_next(index_prev: float, value_prev: float, value_now: float, inflow_today: float) -> float:
    """Advance a time-weighted performance index by one day. Deposits are removed first, so new money
    never counts as a gain and never hides a loss."""
    if value_prev <= 0:
        return index_prev
    return index_prev * ((value_now - inflow_today) / value_prev)


def drawdown_paused(performance_index: float, peak_index: float, profile: Profile) -> bool:
    """True when the time-weighted performance index is at least ``drawdown_pause`` below its peak.

    Pass the performance index (deposits removed), not raw account value: with regular deposits the raw
    value can keep rising while the investments fall, so a raw-value check would never fire."""
    if peak_index <= 0:
        return False
    return performance_index <= peak_index * (1 - profile.drawdown_pause) + 1e-9


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
    correlation: float = 0.0   # 60-day correlation with current holdings (0 when nothing is held)


def rank(ideas: list[Idea], profile: Profile) -> list[Idea]:
    """Aggressive: highest expected return first. Moderate: most stars first, then expected return.
    Ties go to the idea least correlated with what you already hold (never alphabetical)."""
    if profile.rank_by == "expected_return":
        return sorted(ideas, key=lambda i: (-i.expected_return, i.correlation, -i.stars, i.symbol))
    return sorted(ideas, key=lambda i: (-i.stars, -i.expected_return, i.correlation, i.symbol))


def holdings_correlation(candidate: "pd.Series", holdings: dict[str, "pd.Series"], weights: dict[str, float],
                         lookback: int = 60) -> float:
    """Correlation of a candidate's daily returns with the value-weighted returns of current holdings."""
    import pandas as pd

    if not holdings or sum(weights.values()) <= 0:
        return 0.0
    rets = pd.DataFrame({k: v.pct_change() for k, v in holdings.items()}).tail(lookback)
    w = pd.Series(weights).reindex(rets.columns).fillna(0)
    port = (rets * (w / w.sum())).sum(axis=1, min_count=1)
    cand = candidate.pct_change().reindex(rets.index)
    both = pd.concat([cand, port], axis=1).dropna()
    if len(both) < lookback // 2:
        return 0.0
    c = both.iloc[:, 0].corr(both.iloc[:, 1])
    return 0.0 if pd.isna(c) else float(c)


def fit_score(correlation: float, steps: list[float]) -> int:
    """Fit sub-score 0-5: 5 minus the number of correlation steps exceeded."""
    return 5 - sum(correlation > s for s in steps)


@dataclass(frozen=True)
class GoalCheck:
    ready: bool            # enough history to judge
    behind: bool           # short-term trading earned less than the benchmark over the window
    short_term_return: Optional[float]
    benchmark_return: Optional[float]


def short_term_vs_benchmark(
    bucket_value: "pd.Series",
    bucket_inflows: "pd.Series",
    benchmark_closes: "pd.DataFrame",
    window: int,
) -> GoalCheck:
    """Time-weighted return of the short-term bucket (cash + positions, deposits removed) against an
    equal-weight hold of the benchmark funds, over the last ``window`` sessions."""
    import pandas as pd

    v = bucket_value.dropna()
    if len(v) <= window:
        return GoalCheck(False, False, None, None)
    flows = bucket_inflows.reindex(v.index, fill_value=0.0)
    daily = ((v - flows) / v.shift(1) - 1).iloc[1:].tail(window)
    if daily.isna().any() or (v.shift(1).tail(window) <= 0).any():
        return GoalCheck(False, False, None, None)
    st_ret = float((1 + daily).prod() - 1)
    b = benchmark_closes.reindex(v.index).ffill().pct_change().iloc[1:].tail(window).mean(axis=1)
    bench_ret = float((1 + b.fillna(0)).prod() - 1)
    return GoalCheck(True, st_ret < bench_ret, st_ret, bench_ret)
