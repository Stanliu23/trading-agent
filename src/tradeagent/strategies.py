"""Strategy rules for the experiments (each in its own Alpaca paper account). Same rules as the 2026-11-23 tournament
(research/strategy_tournament.py); a test checks they pick the same stocks.

Both rank the 77 traded stocks at the close of the last session of a month and hold the top 10, 10% each:
- MOM  (stock momentum, Jegadeesh & Titman 1993): highest return from 12 months ago (252 sessions) to 1 month ago
  (21 sessions); the last month is skipped.
- LOWV (low volatility, Blitz & van Vliet 2007): lowest standard deviation of daily returns over the last 252 sessions.
Both FAILED the pass bar (see docs/REPLAY_FINDINGS.md, "Strategy tournament"); they run as labelled experiments only.
"""

from __future__ import annotations

from datetime import date

import pandas as pd

TOP_N = 10
NAMES = {"MOM": "Stock momentum", "LOWV": "Low volatility"}
RULES = {"MOM": "Each month, hold the 10 of the 77 traded stocks with the best return from 12 months ago to 1 month "
                "ago, 10% each.",
         "LOWV": "Each month, hold the 10 of the 77 traded stocks with the calmest daily moves over the last year, "
                 "10% each."}


def closes(bars: dict[str, pd.DataFrame], symbols: list[str]) -> pd.DataFrame:
    """Close prices on SPY's trading days, carried forward over gaps (as in the backtest)."""
    cal = bars["SPY"].index
    return pd.DataFrame({s: bars[s]["close"] for s in symbols if s in bars}).reindex(cal).ffill()


def signal_day(index: pd.DatetimeIndex, today: date) -> pd.Timestamp:
    """The last session of the month before ``today``'s month: the close the ranking is read at."""
    first = pd.Timestamp(today.replace(day=1))
    before = index[index < first]
    if len(before) == 0:
        raise ValueError("no price history before this month")
    return before[-1]


def ranking(strategy: str, c: pd.DataFrame, day: pd.Timestamp) -> list[str]:
    """Every stock, best first, at the close of ``day``."""
    i = c.index.get_loc(day)
    if i < 252:
        raise ValueError(f"{strategy} needs 252 sessions of history before {day:%Y-%m-%d}")
    if strategy == "MOM":
        r = (c.iloc[i - 21] / c.iloc[i - 252] - 1).dropna()
        return list(r.sort_values(ascending=False, kind="stable").index)
    if strategy == "LOWV":
        v = c.pct_change().iloc[i - 251:i + 1].std().dropna()
        return list(v.sort_values(ascending=True, kind="stable").index)
    raise ValueError(strategy)


# Today's GICS sectors of the 77 traded stocks (used by the momentum sector cap, idea 2026-11-23-5).
SECTOR = {
    **dict.fromkeys(["AAPL", "MSFT", "NVDA", "CSCO", "ORCL", "ADBE", "CRM", "INTC", "AMD", "QCOM", "TXN", "AVGO", "MU",
                     "AMAT", "LRCX", "KLAC", "ADI", "MRVL", "NXPI", "INTU", "NOW", "IBM", "ACN"], "Information Technology"),
    **dict.fromkeys(["GOOGL", "META", "NFLX", "DIS", "T", "VZ", "CMCSA"], "Communication Services"),
    **dict.fromkeys(["AMZN", "HD", "MCD", "NKE", "LOW", "SBUX", "BKNG"], "Consumer Discretionary"),
    **dict.fromkeys(["PG", "KO", "PEP", "COST", "WMT", "TGT"], "Consumer Staples"),
    **dict.fromkeys(["JPM", "V", "MA", "BAC", "WFC", "GS", "MS", "BLK", "AXP"], "Financials"),
    **dict.fromkeys(["UNH", "JNJ", "MRK", "ABBV", "PFE", "LLY", "TMO", "AMGN", "GILD", "BMY", "ISRG"], "Health Care"),
    **dict.fromkeys(["XOM", "CVX", "COP", "SLB"], "Energy"),
    **dict.fromkeys(["UNP", "CAT", "DE", "HON", "GE", "LMT", "RTX"], "Industrials"),
    **dict.fromkeys(["NEE", "DUK"], "Utilities"),
    "LIN": "Materials",
}
SECTOR_CAP_IDEA = "2026-11-23-5"
SECTOR_CAP = 3


def targets(strategy: str, c: pd.DataFrame, day: pd.Timestamp, blocked: set[str] = frozenset(),
            sector_cap: int | None = None) -> list[str]:
    """The 10 stocks to hold, skipping any you sold yourself (the next-ranked one takes its place). With
    ``sector_cap``, at most that many from one GICS sector: a stock whose sector is full is skipped too."""
    picks, count = [], {}
    for s in ranking(strategy, c, day):
        if s in blocked:
            continue
        sec = SECTOR.get(s, s)
        if sector_cap is not None and count.get(sec, 0) >= sector_cap:
            continue
        picks.append(s)
        count[sec] = count.get(sec, 0) + 1
        if len(picks) == TOP_N:
            break
    return picks
