"""Per-trade simulator: one open position per symbol per setup, daily bars, no look-ahead.

Fill rules (conservative):
- entry at the open after the signal close;
- if a later open gaps through the stop, exit at that open (worse than the stop);
- if a day touches both stop and target, assume the stop was hit first;
- a signal exit is read at a close and filled at the next open;
- the time exit fills at the close of the last allowed day.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd

from tradeagent.setups import indicators as ind
from tradeagent.setups.library import Setup


@dataclass(frozen=True)
class Trade:
    setup_id: str
    symbol: str
    entry_date: pd.Timestamp
    exit_date: pd.Timestamp
    entry: float
    exit: float
    stop: Optional[float]
    ret: float               # after round-trip cost
    r: Optional[float]       # return in units of entry-to-stop risk, after cost
    reason: str              # stop | target | signal | time | end | horizon
    hold_days: int


def _bool(series: pd.Series) -> np.ndarray:
    return series.fillna(False).astype(bool).to_numpy()


def simulate_swing(df: pd.DataFrame, setup: Setup, symbol: str, cost: float) -> list[Trade]:
    if setup.kind != "swing":
        raise ValueError(f"{setup.id} is not a swing setup")
    o, h, l, c = (df[k].to_numpy(dtype=float) for k in ("open", "high", "low", "close"))
    dates = df.index
    sig = _bool(setup.signal(df))
    ex = _bool(setup.exit_signal(df)) if setup.exit_signal else np.zeros(len(df), bool)
    a = ind.atr(df, 14).to_numpy()
    trades: list[Trade] = []
    i, n = 0, len(df)
    while i < n - 1:
        if not sig[i]:
            i += 1
            continue
        e_idx = i + 1
        entry = o[e_idx]
        if setup.stop_from_signal_low:
            stop = l[i]
        else:
            if np.isnan(a[i]):
                i += 1
                continue
            stop = entry - setup.stop_atr * a[i]
        risk = entry - stop
        if not (risk > 0 and entry > 0):
            i += 1
            continue
        if setup.target_r is not None:
            target = entry + setup.target_r * risk
        elif setup.target_atr is not None:
            target = entry + setup.target_atr * a[i]
        else:
            target = None

        exit_px = exit_idx = reason = None
        j = e_idx
        while j < n:
            if j > e_idx and o[j] <= stop:
                exit_px, exit_idx, reason = o[j], j, "stop"
            elif l[j] <= stop:
                exit_px, exit_idx, reason = stop, j, "stop"
            elif target is not None and j > e_idx and o[j] >= target:
                exit_px, exit_idx, reason = o[j], j, "target"
            elif target is not None and h[j] >= target:
                exit_px, exit_idx, reason = target, j, "target"
            elif ex[j]:
                if j + 1 < n:
                    exit_px, exit_idx, reason = o[j + 1], j + 1, "signal"
                else:
                    exit_px, exit_idx, reason = c[j], j, "end"
            elif setup.max_hold_days and (j - e_idx + 1) >= setup.max_hold_days:
                exit_px, exit_idx, reason = c[j], j, "time"
            if reason:
                break
            if setup.breakeven_after_r is not None and h[j] >= entry + setup.breakeven_after_r * risk:
                stop = max(stop, entry)  # takes effect from the next session (intraday order is unknown)
            j += 1
        if reason is None:
            exit_px, exit_idx, reason = c[n - 1], n - 1, "end"

        ret = exit_px / entry - 1 - cost
        trades.append(Trade(setup.id, symbol, dates[e_idx], dates[exit_idx], float(entry), float(exit_px),
                            float(stop), float(ret), float(ret * entry / risk), reason, exit_idx - e_idx + 1))
        i = exit_idx  # a new signal may fire at the exit day's close
    return trades


def simulate_accumulate(df: pd.DataFrame, setup: Setup, symbol: str, cost: float, horizon: int) -> list[Trade]:
    """Each signal day: buy at the open, measure the return `horizon` trading days later."""
    if setup.kind != "accumulate":
        raise ValueError(f"{setup.id} is not an accumulate setup")
    o, c = df["open"].to_numpy(dtype=float), df["close"].to_numpy(dtype=float)
    sig = _bool(setup.signal(df))
    trades = []
    for i in np.flatnonzero(sig):
        k = i + horizon - 1
        if k >= len(df):
            break
        ret = c[k] / o[i] - 1 - cost
        trades.append(Trade(setup.id, symbol, df.index[i], df.index[k], float(o[i]), float(c[k]),
                            None, float(ret), None, "horizon", horizon))
    return trades


def simulate(df: pd.DataFrame, setup: Setup, symbol: str, cost: float, horizon: int) -> list[Trade]:
    if setup.kind == "swing":
        return simulate_swing(df, setup, symbol, cost)
    return simulate_accumulate(df, setup, symbol, cost, horizon)
