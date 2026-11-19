from datetime import date, datetime, timezone

import numpy as np
import pandas as pd
import pytest

from tradeagent import impact
from tradeagent.config import load_config


@pytest.fixture(scope="module")
def cfg():
    return load_config()


def test_kind_priority():
    assert impact.kind_of("2.02,9.01") == "earnings"
    assert impact.kind_of("5.02,8.01,9.01") == "management change"
    assert impact.kind_of("4.02,2.02") == "restatement"
    assert impact.kind_of("9.01") is None


def test_event_session_after_close_moves_to_next_day():
    # 21:30 UTC on Mon Nov 9 2026 = 16:30 ET -> next session Tue Nov 10
    assert impact.event_session(datetime(2026, 11, 9, 21, 30, tzinfo=timezone.utc)) == date(2026, 11, 10)
    # 14:00 UTC = 09:00 ET, before the open -> same day
    assert impact.event_session(datetime(2026, 11, 9, 14, 0, tzinfo=timezone.utc)) == date(2026, 11, 9)
    # Wed Nov 25 after close -> Thanksgiving closed -> Fri Nov 27
    assert impact.event_session(datetime(2026, 11, 25, 22, 0, tzinfo=timezone.utc)) == date(2026, 11, 27)


def _bars(closes, start="2025-01-02"):
    idx = pd.bdate_range(start, periods=len(closes))
    c = pd.Series(closes, index=idx, dtype=float)
    return pd.DataFrame({"open": c, "high": c, "low": c, "close": c, "volume": 1e6})


def test_abnormal_return_vs_spy():
    stock = _bars([100, 100, 110, 110, 110, 110, 110, 110])
    spy = _bars([100, 100, 101, 101, 101, 101, 101, 101])
    day = stock.index[2].date()
    assert impact.abnormal_return(stock, spy, day, 5) == pytest.approx(0.10 - 0.01)
    assert impact.abnormal_return(stock, spy, stock.index[6].date(), 5) is None   # not enough days after


def test_measured_needs_count_size_and_consistency(cfg):
    n = 30
    closes, days = [100.0], []
    for k in range(n):                      # each event: +3% jump that holds, separated by flat days
        closes += [closes[-1]] * 8
        days.append(len(closes))
        closes += [closes[-1] * 1.03] * 6
    stock = _bars(closes)
    spy = _bars([100.0] * len(closes))
    bars = {"X": stock, "SPY": spy}
    sessions = [stock.index[i].date() for i in days]
    res = impact.measure("earnings", "X", sessions, bars, cfg)
    assert res.n == n and res.measured and res.median == pytest.approx(0.03, abs=1e-9)
    few = impact.measure("earnings", "X", sessions[:5], bars, cfg)
    assert few.n == 5 and not few.measured                          # fewer than 10 events
    cut = impact.measure("earnings", "X", sessions, bars, cfg, before=sessions[3])
    assert cut.n == 3                                               # never uses events after the cutoff
    assert "measured impact" in res.line() and "context only" in few.line()


def test_pooled_fallback(cfg):
    a = _bars([100, 100, 103, 103, 103, 103, 103, 103] * 3)
    spy = _bars([100.0] * len(a))
    bars = {"A": a, "B": a.copy(), "SPY": spy}
    day = a.index[2].date()
    res = impact.measure("earnings", "A", [day], bars, cfg, pooled={"A": [day], "B": [day]})
    assert res.scope.startswith("pooled") and res.n == 2
