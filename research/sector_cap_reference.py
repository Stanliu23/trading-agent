"""Removal threshold for the momentum sector cap trial (idea 2026-11-23-5): the 5th percentile of 6-month
capped-minus-uncapped gaps, 2015-2025, measured exactly as the live check measures them (trial_checks.py).
Writes research/results/sector_cap_reference.json.  Run: uv run python research/sector_cap_reference.py"""
import json
import pandas as pd
from tradeagent import prices, strategies, trial_checks
from tradeagent.setups.library import TRADED_STOCKS

bars, missing = prices.daily_bars(sorted(set(TRADED_STOCKS) | {"SPY"}), "2014-01-01", "2026-11-20")
assert not missing, missing
c = strategies.closes(bars, list(TRADED_STOCKS))
gaps = trial_checks.sector_cap_gaps(c, end=pd.Timestamp("2025-12-31"))
six = gaps.rolling(trial_checks.MONTHS).sum().dropna()
out = {"made": "2026-11-23", "months": len(gaps), "six_month_windows": len(six),
       "threshold_6m_log_gap": float(six.quantile(0.05)), "median_6m_log_gap": float(six.median()),
       "first": str(gaps.index[0].date()), "last": str(gaps.index[-1].date())}
trial_checks.SECTOR_REF.write_text(json.dumps(out, indent=1))
print(out)
