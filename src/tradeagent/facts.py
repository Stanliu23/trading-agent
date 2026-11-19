"""Build the measured facts behind an alert. These are what the analyst may write from; nothing else."""

from __future__ import annotations

from datetime import date
from typing import Optional

import pandas as pd

from tradeagent.analyst import Fact
from tradeagent.setups import indicators as ind


def _d(ts) -> str:
    return pd.Timestamp(ts).strftime("%b %d %Y")


def signal_fact(setup_id: str, symbol: str, df: pd.DataFrame, day: pd.Timestamp) -> Fact:
    """Why the setup fired on ``day`` (signal close), in numbers taken from the price history."""
    i = df.index.get_loc(day)
    c = df["close"]
    src = f"prices {pd.Timestamp(day):%m-%d}"
    if setup_id == "S2":
        vr = df["volume"].iloc[i] / ind.sma(df["volume"], 50).iloc[i]
        return Fact("signal", f"{symbol} closed at ${c.iloc[i]:,.2f} on {_d(day)}, its highest close in 52 weeks, "
                              f"on {vr:.1f}x its 50-day average volume.", src)
    if setup_id == "S3":
        lb, ma = ind.bollinger_lower(c, 20, 2.0).iloc[i], ind.sma(c, 200).iloc[i]
        return Fact("signal", f"{symbol} closed at ${c.iloc[i]:,.2f} on {_d(day)}, below its lower Bollinger band "
                              f"(${lb:,.2f}) while above its 200-day average (${ma:,.2f}).", src)
    if setup_id == "S4":
        gap = df["open"].iloc[i] / c.iloc[i - 1] - 1
        vr = df["volume"].iloc[i] / ind.sma(df["volume"], 50).shift(1).iloc[i]
        return Fact("signal", f"{symbol} opened {gap:.1%} above the prior close on {_d(day)} on {vr:.1f}x average "
                              f"volume and closed at ${c.iloc[i]:,.2f}.", src)
    raise ValueError(setup_id)


def odds_fact(setup_id: str, stats: dict) -> Fact:
    return Fact("odds", f"{stats['n']} past {setup_id} trades: {1 - stats['loss_rate']:.0%} positive, average "
                        f"{stats['mean_ret']:+.2%}, 1 in 20 worse than {stats['tail_ret']:.1%}.", f"setup {setup_id}")


def plan_fact(setup_id: str, entry: float, stop: Optional[float], target: Optional[float], max_hold: Optional[int]) -> Fact:
    parts = []
    if stop:
        parts.append(f"stop ${stop:,.2f} ({(entry - stop) / entry:.1%} below ${entry:,.2f})")
    if target:
        parts.append(f"target ${target:,.2f} ({target / entry - 1:.1%} above)")
    if max_hold:
        parts.append(f"time limit {max_hold} trading days")
    return Fact("plan", "Plan: " + ", ".join(parts) + ".", f"setup {setup_id} rules")


def earnings_fact(symbol: str, next_date: Optional[date], exit_day: Optional[date]) -> Optional[Fact]:
    if next_date is None:
        return None
    when = "after" if exit_day and next_date > exit_day else "before"
    return Fact("earnings", f"{symbol} next reports earnings on {_d(next_date)}, {when} the planned exit.",
                "Yahoo earnings calendar")


def exit_facts(symbol: str, setup_id: str, reason: str, entry_day, entry: float, exit_day, exit_px: float,
               stop: Optional[float], target: Optional[float], max_hold: Optional[int], pending: bool = False) -> list[Fact]:
    """``pending``: the sell is still to be done (digest); otherwise it already happened (alerts, reports)."""
    why = {"stop": f"{symbol} traded down to its stop at ${stop:,.2f} on {_d(exit_day)}." if stop else "",
           "target": f"{symbol} reached its target of ${target:,.2f} on {_d(exit_day)}." if target else "",
           "signal": f"{symbol}'s exit rule fired: it closed back above its 20-day average before {_d(exit_day)}.",
           "time": f"{symbol} reached its {max_hold}-trading-day time limit on {_d(exit_day)}."}[reason]
    return [Fact("exit", why, f"setup {setup_id} rules"),
            Fact("result", (f"Bought at ${entry:,.2f} on {_d(entry_day)}; now ${exit_px:,.2f}: {exit_px / entry - 1:+.1%} so far."
                            if pending else
                            f"Bought at ${entry:,.2f} on {_d(entry_day)}; sold at ${exit_px:,.2f}: "
                            f"{exit_px / entry - 1:+.1%} before costs."), f"prices {pd.Timestamp(exit_day):%m-%d}")]
