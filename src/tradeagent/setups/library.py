"""The fixed setup library. Every rule is written down here; nothing is tuned to the data.

Parameters are textbook defaults chosen before any backtest was run. Changing one
means re-running the backtest and getting Stanley's approval again.

Timing convention for every short-term setup:
- the signal is read at the close of day t;
- entry is at the open of day t+1;
- stop/target are checked from the entry day on, using that day's high/low.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Literal, Optional

import pandas as pd

from tradeagent.setups import indicators as ind

ETFS = ["SPY", "QQQ", "IWM", "DIA", "VTI", "SCHD", "XLK", "XLF", "XLE", "XLV", "XLI", "XLY",
        "XLP", "XLU", "XLB", "EFA", "EEM", "TLT", "IEF", "GLD"]

# Current large caps. Survivorship bias: these are today's winners, so stock-setup
# results are optimistic. The stats table flags it.
STOCKS = ["AAPL", "MSFT", "AMZN", "GOOGL", "META", "NVDA", "JPM", "V", "MA", "UNH", "JNJ", "PG",
          "HD", "XOM", "CVX", "KO", "PEP", "COST", "WMT", "MRK", "ABBV", "PFE", "CSCO", "ORCL",
          "ADBE", "CRM", "INTC", "AMD", "QCOM", "TXN", "AVGO", "NFLX", "DIS", "MCD", "NKE",
          "BAC", "WFC", "LLY", "TMO", "UNP"]

# Added to S2 and S4 on 2026-11-20 (you approved; 36-start check passed, see REPLAY_FINDINGS "97 short-term symbols").
# Chosen 2026-11-18 before any results.
ADDED_STOCKS = ["MU", "AMAT", "LRCX", "KLAC", "ADI", "MRVL", "NXPI", "INTU", "NOW", "IBM", "ACN",
                "GS", "MS", "BLK", "AXP", "CAT", "DE", "HON", "GE", "LMT", "RTX",
                "LOW", "SBUX", "TGT", "BKNG", "AMGN", "GILD", "BMY", "ISRG",
                "NEE", "DUK", "COP", "SLB", "LIN", "T", "VZ", "CMCSA"]
TRADED_STOCKS = STOCKS + ADDED_STOCKS          # every stock a short-term setup can buy

# SPY dropped 2026-11-18: near-duplicate of VTI.
CORE_ETFS = ["VTI", "QQQ", "SCHD"]

Signal = Callable[[pd.DataFrame], pd.Series]


@dataclass(frozen=True)
class Setup:
    id: str
    name: str
    bucket: Literal["short_term", "long_term"]
    kind: Literal["swing", "accumulate"]
    universe: tuple[str, ...]
    rule: str                                   # plain-English rule shown in emails
    signal: Signal
    stop_atr: Optional[float] = None            # stop distance in ATR(14) at signal close
    target_atr: Optional[float] = None          # target distance in ATR(14); None = no fixed target
    exit_signal: Optional[Signal] = None        # exit at next open when true at a close
    max_hold_days: Optional[int] = None         # time exit at that day's close
    stop_from_signal_low: bool = False          # stop at the signal day's low instead of ATR
    target_r: Optional[float] = None            # target as a multiple of the entry-to-stop risk
    breakeven_after_r: Optional[float] = None   # once a day's high reaches entry + this many R, the stop moves up to the entry price (from the next day)
    trail_atr: Optional[float] = None           # trailing stop: max(stop, highest close since entry - this x ATR(14) at the signal close), from the next day
    profit_close_pct: Optional[float] = None    # sell at the next open after the first close at or above entry x (1 + this)
    max_open: Optional[int] = None              # at most this many positions of this setup open or queued at once (account)
    goal_exempt: bool = False                   # its profit/loss is left out of the goal check (it cannot cause a goal pause)
    notes: tuple[str, ...] = field(default_factory=tuple)
    logic: str = ""                             # why the setup should work, shown as 'Why buy' in emails


# --- short-term ---------------------------------------------------------------

def _pullback_signal(df):
    c = df["close"]
    return (c > ind.sma(c, 200)) & (ind.rsi(c, 2) < 10)


def _pullback_exit(df):
    c = df["close"]
    return c > ind.sma(c, 5)


def _breakout_signal(df):
    c, v = df["close"], df["volume"]
    new_high = c >= c.rolling(252, min_periods=252).max()
    return new_high & (v > 1.5 * ind.sma(v, 50)) & (c > ind.sma(c, 200))


def _etf_reversion_signal(df):
    c = df["close"]
    return (c < ind.bollinger_lower(c, 20, 2.0)) & (c > ind.sma(c, 200))


def _etf_reversion_exit(df):
    c = df["close"]
    return c > ind.sma(c, 20)


def _gap_signal(df):
    prev = df["close"].shift(1)
    gap = df["open"] / prev - 1
    rng = (df["high"] - df["low"]).replace(0, float("nan"))
    closed_strong = (df["close"] - df["low"]) / rng >= 0.5
    return (gap >= 0.04) & (df["volume"] >= 3 * ind.sma(df["volume"], 50).shift(1)) & closed_strong


# --- long-term ----------------------------------------------------------------

def _month_start(df):
    idx = df.index
    first = pd.Series(idx.to_period("M"), index=idx)
    return first != first.shift(1)


LIBRARY: tuple[Setup, ...] = (
    Setup(
        id="S1", name="Trend pullback", bucket="short_term", kind="swing",
        universe=tuple(STOCKS + ETFS),
        rule="Price above its 200-day average and 2-day RSI below 10. Exit when the close is back above "
             "the 5-day average, at a 2.5×ATR stop, or after 10 days.",
        logic="Short, sharp drops in a stock that is still in a long uptrend have tended to bounce back.",
        signal=_pullback_signal, exit_signal=_pullback_exit, stop_atr=2.5, max_hold_days=10,
    ),
    Setup(
        id="S2", name="52-week-high breakout", bucket="short_term", kind="swing",
        universe=tuple(TRADED_STOCKS),
        rule="Close at a 52-week high on volume 1.5× its 50-day average, above the 200-day average. "
             "Stop 2×ATR, target 4×ATR, exit after 20 days.",
        logic="Stocks breaking to a 1-year high on heavy buying have tended to keep rising for weeks (momentum); "
              "wins have averaged about twice the size of losses.",
        signal=_breakout_signal, stop_atr=2.0, target_atr=4.0, max_hold_days=20,
    ),
    Setup(
        id="S3", name="ETF dip in uptrend", bucket="short_term", kind="swing",
        universe=tuple(ETFS),
        rule="ETF closes below its lower Bollinger band (20, 2) while above its 200-day average. "
             "Exit when the close is back above the 20-day average, at a 3×ATR stop, or after 15 days.",
        logic="A diversified fund that dips unusually far while its long trend is up has tended to recover, "
              "because no single company's news drags it down.",
        signal=_etf_reversion_signal, exit_signal=_etf_reversion_exit, stop_atr=3.0, max_hold_days=15,
    ),
    Setup(
        id="S4", name="Big gap-up continuation", bucket="short_term", kind="swing",
        universe=tuple(TRADED_STOCKS),
        rule="Opens ≥4% above the prior close on 3× average volume and closes in the top half of its range "
             "(usually earnings). Stop at that day's low, target 2× the risk, exit after 20 days.",
        logic="After a strong earnings surprise, big investors have tended to keep buying for weeks "
              "(post-earnings drift).",
        signal=_gap_signal, stop_from_signal_low=True, target_r=2.0, max_hold_days=20,
        notes=("Proxy for post-earnings drift: no historical earnings dates in the free data.",),
    ),
    Setup(
        id="L1", name="Core index accumulation", bucket="long_term", kind="accumulate",
        universe=tuple(CORE_ETFS),
        rule="Buy broad index ETFs (VTI, QQQ, SCHD) with each deposit, into whichever is held least. "
             "Sell only on a measured thesis break, never on price noise.",
        logic="Over 3-year spans, broad stock index funds have been positive in 92% of start dates since 2005; "
              "steady monthly buying spreads out the timing risk.",
        signal=_month_start,
        notes=("Scored on 3-year forward returns from every month start; windows overlap, so "
               "Confidence is capped at 2.",),
    ),
)


def get(setup_id: str) -> Setup:
    for s in LIBRARY:
        if s.id == setup_id:
            return s
    raise KeyError(setup_id)


# --- experiments only (never in LIBRARY, so the main account never uses them) -------------------------------------------

def _big_dip_signal(df):
    c = df["close"]
    level = 0.70 * c.rolling(60, min_periods=60).max()
    return (c <= level) & (c.shift(1) > level.shift(1))


# Big-dip D2 (idea 2026-11-23-6): failed the account test; runs as a labelled experiment in a 25% slice of the
# low-volatility paper account (Stanley's choice, 2026-11-23). Rules exactly as tested.
DIP_D2 = Setup(
    id="D2", name="Big-dip rebound, quick profit", bucket="short_term", kind="swing", universe=tuple(TRADED_STOCKS),
    rule="A stock's first close 30% or more below its highest close of the last 60 sessions. Sell the morning after the "
         "first close 3% above the buy price; stop 2.5xATR; out after 20 sessions. One at a time.",
    logic="Large caps that fall 30% in a few weeks have often bounced within days.",
    signal=_big_dip_signal, stop_atr=2.5, max_hold_days=20, profit_close_pct=0.03, max_open=1, goal_exempt=True,
)
