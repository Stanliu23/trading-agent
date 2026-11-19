"""The shadow account as of a given day: every rule replayed from the shadow start date on real prices."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional

import pandas as pd

from tradeagent import market, prices
from tradeagent.config import PROJECT_ROOT, Config
from tradeagent.papertrade import Position, SimResult, simulate_with_goal_rules
from tradeagent.setups.library import CORE_ETFS, ETFS, STOCKS, get

EARNINGS_CACHE = PROJECT_ROOT / "data" / "earnings.json"


class NotStarted(Exception):
    """The shadow run has no trading session yet (start date is in the future or today's close isn't in)."""


def earnings_dates(symbols: list[str], max_age_days: int = 7) -> dict[str, list[date]]:
    """Past and next earnings dates per stock (Yahoo), cached and refreshed weekly."""
    cache = {}
    if EARNINGS_CACHE.exists():
        cache = json.loads(EARNINGS_CACHE.read_text())
    fresh = cache.get("_fetched") and date.fromisoformat(cache["_fetched"]) >= date.today() - timedelta(days=max_age_days)
    if not fresh:
        for s in symbols:
            got = market.past_earnings(s, limit=60)
            if got:
                cache[s] = [d.isoformat() for d in got]
            time.sleep(0.12)
        cache["_fetched"] = date.today().isoformat()
        EARNINGS_CACHE.parent.mkdir(parents=True, exist_ok=True)
        EARNINGS_CACHE.write_text(json.dumps(cache))
    return {k: [date.fromisoformat(d) for d in v] for k, v in cache.items() if not k.startswith("_")}


@dataclass
class AccountState:
    as_of: date
    sim: SimResult
    bars: dict[str, pd.DataFrame]
    earnings: dict[str, list[date]]
    stats: dict[str, dict]

    @property
    def day(self) -> pd.Timestamp:
        return self.sim.daily.index[-1]

    def price(self, symbol: str) -> Optional[float]:
        df = self.bars.get(symbol)
        return None if df is None or self.day not in df.index else float(df.at[self.day, "close"])

    def value(self) -> float:
        return float(self.sim.daily["value"].iloc[-1])

    def sells_tomorrow(self) -> list[dict]:
        """Exit signals fire at tomorrow's open; time limits end at tomorrow's close."""
        out = []
        for p in self.sim.open_positions:
            if p.bucket != "short_term":
                continue
            px = self.price(p.symbol) or p.entry
            base = {"position": p, "price": px, "value": p.qty * px, "result": px / p.entry - 1}
            if p.pending_exit:
                out.append({**base, "when": "open", "reason": "signal"})
            elif p.max_hold and p.sessions_held == p.max_hold - 1:
                out.append({**base, "when": "close", "reason": "time"})
        return out

    def next_earnings(self, symbol: str) -> Optional[date]:
        upcoming = [d for d in self.earnings.get(symbol, []) if d > self.day.date()]
        return min(upcoming) if upcoming else None


def load_bars(config: Config, start: str) -> dict[str, pd.DataFrame]:
    """Daily bars for everything the account can touch, fetched once up to today (cached per day)."""
    # enough history for 200-day/52-week signals AND the 504-session rate-sensitivity window
    days_needed = max(420, int(config.macro.rate_sensitivity_lookback * 365 / 252) + 30)
    fetch_start = (pd.Timestamp(start) - pd.DateOffset(days=days_needed)).date().isoformat()
    symbols = sorted(set(STOCKS) | set(ETFS) | set(CORE_ETFS) | set(config.paper_watch.stocks)
                     | ({config.cash.park_idle_in} if config.cash.park_idle_in else set()))
    bars, _ = prices.daily_bars(symbols, fetch_start, date.today().isoformat())
    return bars


def build(config: Config, as_of: Optional[date] = None, start: Optional[str] = None,
          bars: Optional[dict[str, pd.DataFrame]] = None) -> AccountState:
    """The account as of ``as_of``. Pass ``bars`` from ``load_bars`` to reuse one download for many dates;
    data after ``as_of`` is cut off so nothing from the future leaks in."""
    as_of = as_of or date.today()
    start = start or config.local.shadow_start or config.shadow.start
    bars = bars if bars is not None else load_bars(config, start)
    cut = pd.Timestamp(as_of)
    bars = {k: v.loc[:cut] for k, v in bars.items()}
    if bars.get("SPY") is None or bars["SPY"].loc[start:].empty:
        raise NotStarted(f"shadow run starts {start}; no closed session yet")
    stats = {d["setup_id"]: d for d in json.loads((PROJECT_ROOT / "data" / "setup_stats.json").read_text())}
    earnings = earnings_dates(list(STOCKS))
    sim = simulate_with_goal_rules(bars, config, stats, start, as_of.isoformat(), config.shadow.start_cash,
                                   config.shadow.monthly_deposit, earnings, plan_next_day=True)
    return AccountState(as_of, sim, bars, earnings, stats)
