import dataclasses

import numpy as np
import pandas as pd

from tradeagent.setups.library import get
from tradeagent.setups.simulate import simulate_swing


def test_trailing_stop_follows_the_best_close_and_exits_on_the_way_down():
    idx = pd.bdate_range("2025-01-01", periods=320)
    base = np.r_[np.linspace(50, 60, 300), [61, 64, 68, 72, 75, 74, 72, 70, 66, 62, 60, 58, 57, 56, 55, 54, 53, 52, 51, 50]]
    vol = np.full(320, 1e6)
    vol[300] = 3e6                                                   # breakout day on heavy volume
    df = pd.DataFrame({"open": base, "high": base + 0.5, "low": base - 0.5, "close": base, "volume": vol}, index=idx)
    s2t = dataclasses.replace(get("S2"), target_atr=None, trail_atr=3.0)
    t = [x for x in simulate_swing(df, s2t, "X", 0.0) if x.entry_date == idx[301]][0]
    atr = 1.0 + 0.0                                                  # high-low range is 1.0 and daily gaps are small
    assert t.reason == "stop" and t.exit_date > idx[305]             # held through the rise, out on the way down
    assert t.exit > t.entry                                          # locked in part of the gain
    plain = [x for x in simulate_swing(df, get("S2"), "X", 0.0) if x.entry_date == idx[301]][0]
    assert plain.reason in ("target", "stop", "time")


def test_profit_exit_sells_the_morning_after_a_close_3pct_up():
    from tradeagent.setups.library import Setup
    idx = pd.bdate_range("2025-01-01", periods=100)
    close = np.r_[np.full(80, 100.0), [69, 70, 71, 72, 73], np.full(15, 73.0)]
    df = pd.DataFrame({"open": close, "high": close + 0.2, "low": close - 0.2, "close": close, "volume": 1e6}, index=idx)
    sig = pd.Series(False, idx)
    sig.iloc[80] = True
    s = Setup(id="DX", name="t", bucket="short_term", kind="swing", universe=("X",), rule="", signal=lambda d: sig,
              stop_atr=2.5, max_hold_days=20, profit_close_pct=0.03)
    t = simulate_swing(df, s, "X", 0.0)[0]
    assert t.entry == 70 and t.reason == "profit" and t.exit_date == idx[85] and t.exit == 73   # 73 >= 72.10, sold next open
