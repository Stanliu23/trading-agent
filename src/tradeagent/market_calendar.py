"""NYSE sessions (holidays, half days) via exchange_calendars' XNYS.

Vibe-Trading's own calendar (src/data_gateway/calendars.py at ebc849b) is a thin
wrapper around this same XNYS calendar, so we use the library directly.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from functools import lru_cache
from zoneinfo import ZoneInfo

import exchange_calendars as xcals
import pandas as pd

NY = ZoneInfo("America/New_York")


@dataclass(frozen=True)
class Session:
    day: date
    open: datetime   # New York time
    close: datetime  # New York time

    @property
    def is_half_day(self) -> bool:
        return self.close.hour < 16


@lru_cache(maxsize=1)
def _calendar() -> xcals.ExchangeCalendar:
    return xcals.get_calendar("XNYS")


def session(day: date) -> Session | None:
    """Return the trading session for ``day``, or None if the market is closed."""
    cal = _calendar()
    label = pd.Timestamp(day)
    if not cal.is_session(label):
        return None
    return Session(
        day=day,
        open=cal.session_open(label).tz_convert(NY).to_pydatetime(),
        close=cal.session_close(label).tz_convert(NY).to_pydatetime(),
    )


def is_trading_day(day: date) -> bool:
    return session(day) is not None


def next_session(after: date) -> Session:
    day = after + timedelta(days=1)
    for _ in range(14):
        found = session(day)
        if found:
            return found
        day += timedelta(days=1)
    raise RuntimeError(f"no NYSE session within 14 days after {after}")


def market_open_at(moment: datetime) -> bool:
    """True if NYSE is in regular trading hours at ``moment`` (timezone-aware)."""
    if moment.tzinfo is None:
        raise ValueError("moment must be timezone-aware")
    local = moment.astimezone(NY)
    found = session(local.date())
    return bool(found and found.open <= local < found.close)
