"""Measured impact: how did past events of the same kind move this stock, beyond the market?

No AI here. Event kinds come from SEC 8-K item codes (and Yahoo earnings dates). For each past event,
the abnormal return is the stock's return minus SPY's, from the close before the event's first trading
session to the close ``horizon`` sessions later. A filing accepted after the 4 pm close counts from the
next session.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Iterable, Optional
from zoneinfo import ZoneInfo

import pandas as pd

from tradeagent import market_calendar
from tradeagent.config import Config

NY = ZoneInfo("America/New_York")

# 8-K item code -> event kind, in priority order (the first match names the filing).
ITEM_KINDS: list[tuple[str, str]] = [
    ("4.02", "restatement"), ("1.05", "cybersecurity incident"), ("2.02", "earnings"),
    ("2.01", "acquisition or sale"), ("1.01", "material agreement"), ("5.02", "management change"),
    ("2.05", "restructuring"), ("2.06", "impairment"), ("3.01", "listing notice"),
    ("7.01", "public disclosure"), ("8.01", "other event"), ("5.07", "shareholder vote"),
]


def kind_of(items: str) -> Optional[str]:
    codes = {c.strip() for c in (items or "").split(",")}
    for code, kind in ITEM_KINDS:
        if code in codes:
            return kind
    return None


def event_session(accepted: datetime) -> Optional[date]:
    """First NYSE session whose prices can reflect an event made public at ``accepted`` (tz-aware)."""
    local = accepted.astimezone(NY)
    s = market_calendar.session(local.date())
    if s and local < s.close:
        return local.date()
    return market_calendar.next_session(local.date()).day


def abnormal_return(stock: pd.DataFrame, spy: pd.DataFrame, session: date, horizon: int) -> Optional[float]:
    idx = stock.index
    pos = idx.searchsorted(pd.Timestamp(session))
    if pos == 0 or pos >= len(idx) or idx[pos].date() != session or pos + horizon - 1 >= len(idx):
        return None
    before, after = idx[pos - 1], idx[pos + horizon - 1]
    if before not in spy.index or after not in spy.index:
        return None
    r_stock = stock.at[after, "close"] / stock.at[before, "close"] - 1
    r_spy = spy.at[after, "close"] / spy.at[before, "close"] - 1
    return float(r_stock - r_spy)


@dataclass(frozen=True)
class Impact:
    kind: str
    symbol: str
    scope: str                    # "this stock" or "pooled across traded stocks"
    n: int
    median: Optional[float]       # median abnormal return over the horizon
    same_sign: Optional[float]    # share of events moving in the median's direction
    horizon: int
    measured: bool

    def line(self) -> str:
        if self.n == 0 or self.median is None:
            return f"{self.kind}: no past events to measure; context only."
        verdict = "measured impact" if self.measured else "context only, no measured impact"
        return (f"{self.kind}: past {self.n} similar events ({self.scope}) moved it a median {self.median:+.1%} vs SPY "
                f"over {self.horizon} days, {self.same_sign:.0%} in that direction: {verdict}.")


def _summarise(kind, symbol, scope, rets: list[float], config: Config) -> Impact:
    n = len(rets)
    if n == 0:
        return Impact(kind, symbol, scope, 0, None, None, config.news.impact_horizon_days, False)
    s = pd.Series(rets)
    med = float(s.median())
    same = float(((s > 0) if med >= 0 else (s < 0)).mean())
    nw = config.news
    measured = n >= nw.min_similar_events and abs(med) >= nw.measured_min_abs_median and same >= nw.measured_min_same_sign
    return Impact(kind, symbol, scope, n, med, same, nw.impact_horizon_days, measured)


def measure(kind: str, symbol: str, sessions: Iterable[date], bars: dict[str, pd.DataFrame], config: Config,
            pooled: Optional[dict[str, Iterable[date]]] = None, before: Optional[date] = None) -> Impact:
    """Measured impact of ``kind`` for ``symbol`` from its past event sessions (only those before ``before``).

    If the stock has too few events and pooling is on, use the same kind across ``pooled`` symbols."""
    h = config.news.impact_horizon_days
    spy = bars["SPY"]

    def rets(sym, days):
        out = []
        for d in days:
            if before is not None and d >= before:
                continue
            r = abnormal_return(bars[sym], spy, d, h) if sym in bars else None
            if r is not None:
                out.append(r)
        return out

    own = rets(symbol, sessions)
    if len(own) >= config.news.min_similar_events or not (config.news.pooled_fallback and pooled):
        return _summarise(kind, symbol, "this stock", own, config)
    allr = [r for sym, days in pooled.items() for r in rets(sym, days)]
    return _summarise(kind, symbol, "pooled across traded stocks", allr, config)


def sessions_by_kind(filings: list[dict]) -> dict[str, list[date]]:
    """Group 8-K filings (from SecClient.recent_filings) into event sessions by kind."""
    out: dict[str, list[date]] = {}
    for f in filings:
        if f.get("form") != "8-K" or not f.get("accepted"):
            continue
        kind = kind_of(f.get("items", ""))
        if not kind:
            continue
        accepted = datetime.fromisoformat(f["accepted"].replace("Z", "+00:00"))
        day = event_session(accepted)
        if day:
            out.setdefault(kind, []).append(day)
    return out
