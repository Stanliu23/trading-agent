"""Removal checks for ideas on trial. Importing this module registers them in ``trials.CHECKS``.

Each check compares the new rule with the old one on the same live data and applies the removal rule written in
research/ideas_ledger.json before the trial started.
"""

from __future__ import annotations

import json
import math
from datetime import date
from typing import Optional

import pandas as pd

from tradeagent import strategies, trials
from tradeagent.config import PROJECT_ROOT
from tradeagent.setups.library import TRADED_STOCKS

SECTOR_REF = PROJECT_ROOT / "research" / "results" / "sector_cap_reference.json"
MONTHS = 6


def _month_ends(index: pd.DatetimeIndex) -> list[pd.Timestamp]:
    """Last session of each completed month (the index's final day is left out: its month may not be over)."""
    m = pd.Series(index.to_period("M"), index=index)
    ends = list(index[(m != m.shift(-1)).to_numpy()])
    return ends[:-1]


def sector_cap_gaps(c: pd.DataFrame, start: Optional[pd.Timestamp] = None,
                    end: Optional[pd.Timestamp] = None) -> pd.Series:
    """Per month: log return of the capped picks minus the uncapped picks, equal weight, from the month-end close the
    ranking is read at to the next month-end close. Paper on both sides, so costs and fills do not tilt it."""
    ends = [d for d in _month_ends(c.index) if c.index.get_loc(d) >= 252]
    out = {}
    for d, nxt in zip(ends[:-1], ends[1:]):
        if start is not None and d < start:
            continue
        if end is not None and nxt > end:
            break
        cap = strategies.targets("MOM", c, d, sector_cap=strategies.SECTOR_CAP)
        unc = strategies.targets("MOM", c, d)
        rc = float((c.loc[nxt, cap] / c.loc[d, cap]).mean())
        ru = float((c.loc[nxt, unc] / c.loc[d, unc]).mean())
        out[nxt] = math.log(rc) - math.log(ru)
    return pd.Series(out, dtype=float)


def sector_cap_threshold() -> float:
    return float(json.loads(SECTOR_REF.read_text())["threshold_6m_log_gap"])


def sector_cap_check(conn, bars, config, trial_start: Optional[str]) -> trials.Outcome:
    """Idea 2026-11-23-5. From 6 completed monthly rebalances on: removed if the last 6 months' capped-minus-uncapped
    gap is below the 5th percentile of 6-month gaps in 2015-2025. Before that, only the count is shown."""
    c = strategies.closes(bars, list(TRADED_STOCKS))
    first = strategies.signal_day(c.index, date.fromisoformat(trial_start or "2026-12-01"))
    gaps = sector_cap_gaps(c, start=first)
    if len(gaps) < MONTHS:
        return trials.Outcome("waiting", f"{len(gaps)} of {MONTHS} monthly rebalances measured; not judged until then.")
    last = float(gaps.iloc[-MONTHS:].sum())
    thr = sector_cap_threshold()
    text = (f"last {MONTHS} months capped vs uncapped {math.expm1(last):+.1%}; removal below {math.expm1(thr):+.1%} "
            f"(the worst 5% of 6-month gaps in 2015-2025)")
    return trials.Outcome("remove" if last < thr else "keep_watching", text)


trials.CHECKS[strategies.SECTOR_CAP_IDEA] = sector_cap_check
