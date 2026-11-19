"""Hand-computed cases for the simulator and statistics."""

import pandas as pd
import pytest

from tradeagent.config import load_config
from tradeagent.setups.library import LIBRARY, Setup
from tradeagent.setups.simulate import Trade, simulate_accumulate, simulate_swing
from tradeagent.setups.stats import compute_stats, stars, tier_for

COST = 0.001


def bars(rows):
    """rows: list of (open, high, low, close)."""
    idx = pd.bdate_range("2020-01-06", periods=len(rows))
    return pd.DataFrame(rows, columns=["open", "high", "low", "close"], index=idx).assign(volume=1e6)


def setup_on_day0(**kw):
    base = dict(id="T", name="test", bucket="short_term", kind="swing", universe=("X",), rule="",
                signal=lambda df: pd.Series(df.index == df.index[0], index=df.index),
                stop_from_signal_low=True, target_r=2.0, max_hold_days=5)
    base.update(kw)
    return Setup(**base)


def test_target_hit():
    # day0 signal, low 95 -> stop 95; entry day1 open 100 -> risk 5, target 110
    df = bars([(99, 100, 95, 99), (100, 105, 98, 104), (104, 111, 103, 109), (109, 110, 108, 109)])
    (t,) = simulate_swing(df, setup_on_day0(), "X", COST)
    assert (t.entry, t.stop, t.exit, t.reason, t.hold_days) == (100, 95, 110, "target", 2)
    assert t.ret == pytest.approx(0.099)
    assert t.r == pytest.approx(1.98)


def test_gap_through_stop_exits_at_open():
    df = bars([(99, 100, 95, 99), (100, 101, 97, 98), (90, 92, 89, 91)])
    (t,) = simulate_swing(df, setup_on_day0(), "X", COST)
    assert (t.exit, t.reason) == (90, "stop")
    assert t.ret == pytest.approx(-0.101)
    assert t.r == pytest.approx(-2.02)


def test_stop_wins_when_both_touched_same_day():
    df = bars([(99, 100, 95, 99), (100, 101, 97, 98), (100, 112, 94, 100)])
    (t,) = simulate_swing(df, setup_on_day0(), "X", COST)
    assert (t.exit, t.reason) == (95, "stop")


def test_time_exit_at_close_of_last_day():
    quiet = (100, 101, 99, 100)
    df = bars([(99, 100, 95, 99)] + [quiet] * 4 + [(100, 101, 99, 102)] + [quiet] * 2)
    (t,) = simulate_swing(df, setup_on_day0(), "X", COST)
    assert (t.exit, t.reason, t.hold_days) == (102, "time", 5)


def test_signal_exit_fills_next_open():
    exit_day3 = lambda df: pd.Series(df.index == df.index[3], index=df.index)
    s = setup_on_day0(exit_signal=exit_day3, target_r=None)
    df = bars([(99, 100, 95, 99), (100, 101, 99, 100), (100, 101, 99, 100), (100, 101, 99, 101), (103, 104, 102, 103)])
    (t,) = simulate_swing(df, s, "X", COST)
    assert (t.exit, t.reason) == (103, "signal")


def test_no_trade_when_entry_opens_below_stop():
    df = bars([(99, 100, 95, 99), (94, 96, 93, 95), (95, 96, 94, 95)])
    assert simulate_swing(df, setup_on_day0(), "X", COST) == []


def test_accumulate_measures_forward_return():
    s = Setup(id="L", name="acc", bucket="long_term", kind="accumulate", universe=("X",), rule="",
              signal=lambda df: pd.Series(df.index == df.index[0], index=df.index))
    df = bars([(100, 101, 99, 100), (100, 101, 99, 105), (105, 111, 104, 110), (110, 111, 109, 110)])
    (t,) = simulate_accumulate(df, s, "X", COST, horizon=3)
    assert (t.entry, t.exit) == (100, 110)
    assert t.ret == pytest.approx(0.099)


def test_library_ids_unique_and_rules_written():
    ids = [s.id for s in LIBRARY]
    assert len(ids) == len(set(ids))
    assert all(s.rule for s in LIBRARY)
    for s in LIBRARY:
        if s.kind == "swing":
            assert s.stop_atr or s.stop_from_signal_low, f"{s.id} has no stop"
            assert s.max_hold_days, f"{s.id} has no time exit"


# --- stats -----------------------------------------------------------------

def test_tier_boundaries():
    c = load_config()
    # second argument is the 5th-percentile trade
    assert tier_for(0.25, -0.08, c) == 1
    assert tier_for(0.26, -0.05, c) == 2
    assert tier_for(0.20, -0.09, c) == 2
    assert tier_for(0.40, -0.15, c) == 2
    assert tier_for(0.41, -0.05, c) == 3
    assert tier_for(0.30, -0.20, c) == 3


def test_stars_round_half_up():
    assert stars(2, 3, 3) == 3   # 2.67
    assert stars(1, 2, 2) == 2   # 1.67
    assert stars(2, 2, 3) == 2   # 2.33
    assert stars(3, 4, 4) == 4   # 3.67
    assert stars(0, 0, 1) == 0
    with pytest.raises(ValueError):
        stars(6, 0, 0)


def _trades(n, ret, start="2016-01-04", r=0.5):
    dates = pd.bdate_range(start, periods=n, freq="20B")
    return [Trade("S1", "X", d, d, 100, 100 * (1 + ret), 95, ret, r, "signal", 3) for d in dates]


def test_evidence_needs_30_trades():
    c = load_config()
    s = next(x for x in LIBRARY if x.id == "S1")
    st = compute_stats(s, _trades(29, 0.02), 1, c)
    assert not st.passes_evidence and "only 29 trades" in st.evidence_note and st.tier is None


def test_evidence_needs_positive_holdout():
    c = load_config()
    s = next(x for x in LIBRARY if x.id == "S1")
    good = _trades(100, 0.02, start="2015-02-02")          # ends before 2024
    bad = _trades(10, -0.01, start="2024-02-01", r=-0.2)   # held-out losers
    st = compute_stats(s, good + bad, 1, c)
    assert not st.passes_evidence and "held-out" in st.evidence_note


def test_passing_setup_gets_tier_edge_confidence():
    c = load_config()
    s = next(x for x in LIBRARY if x.id == "S1")
    st = compute_stats(s, _trades(140, 0.02, start="2015-02-02"), 1, c)
    assert st.passes_evidence and st.out_n > 0
    assert st.tier == 1                     # never lost, 5th pct +2%
    assert st.edge == 5                     # held-out 0.5R > 0.30
    assert st.confidence == 4               # 2 + (>=100 trades) + (all years positive)


def test_tail_not_worst_sets_tier():
    """One extreme loser among many trades must not by itself push a setup to Tier 3."""
    c = load_config()
    s = next(x for x in LIBRARY if x.id == "S1")
    trades = _trades(139, 0.02, start="2015-02-02") + _trades(1, -0.30, start="2020-06-01", r=-6)
    st = compute_stats(s, trades, 1, c)
    assert st.worst_ret == pytest.approx(-0.30)
    assert st.tail_ret == pytest.approx(0.02)
    assert st.tier == 1


def test_accumulate_holdout_is_last_two_years_of_entries():
    c = load_config()
    s = next(x for x in LIBRARY if x.id == "L1")
    dates = pd.date_range("2005-01-03", "2022-12-01", freq="MS")
    trades = [Trade("L1", "X", d, d, 100, 130, None, 0.30, None, "horizon", 756) for d in dates]
    st = compute_stats(s, trades, 1, c)
    assert st.holdout_start.startswith("2020-12")
    assert st.out_n == 25 and st.passes_evidence   # Dec 2020 through Dec 2022, both ends included
    assert st.confidence <= 2


def test_breakeven_stop_moves_after_plus_1r():
    # entry 100, stop 95 (1R = 5). Day 2 high 105.5 (+1.1R) -> stop moves to 100 from day 3.
    s = setup_on_day0(target_r=None, breakeven_after_r=1.0, max_hold_days=10)
    df = bars([(99, 100, 95, 99), (100, 102, 99, 101), (101, 105.5, 100.5, 104), (103, 103, 99, 99.5), (99, 100, 98, 99)])
    (t,) = simulate_swing(df, s, "X", COST)
    assert (t.exit, t.reason) == (100, "stop")
    assert t.ret == pytest.approx(-COST)
    # without breakeven the same path does not stop out at 100
    (u,) = simulate_swing(df, setup_on_day0(target_r=None, max_hold_days=10), "X", COST)
    assert u.reason != "stop" or u.exit == 95
