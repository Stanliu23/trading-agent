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
