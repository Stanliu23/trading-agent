"""Hand-computed cases for sizing, drawdown pause, deposit split and ranking."""

import pytest

from tradeagent.config import load_config
from datetime import date

from tradeagent.risk import (Idea, bucket_room, drawdown_paused, earnings_blocks_entry, planned_exit_day, rank,
                             size_position, split_deposit)


@pytest.fixture
def profiles():
    c = load_config()
    return c.profiles.aggressive, c.profiles.moderate


def test_risk_capped_size(profiles):
    agg, mod = profiles
    # $300 account, entry 100, stop 95 (5%): aggressive 3% -> $9 loss -> $180 position
    s = size_position(profile=agg, tier=1, account_value=300, entry=100, stop=95, room_usd=1e9, cash_usd=1e9, position_cap_pct=1.0)
    assert (s.size_usd, s.max_loss_usd, s.limited_by) == (180, 9, "risk")
    # Tier 3 uses half the cap: $4.50 loss -> $90
    s = size_position(profile=agg, tier=3, account_value=300, entry=100, stop=95, room_usd=1e9, cash_usd=1e9, position_cap_pct=1.0)
    assert (s.size_usd, s.max_loss_usd) == (90, 4.5)
    # Moderate 2%: $6 loss -> $120
    s = size_position(profile=mod, tier=2, account_value=300, entry=100, stop=95, room_usd=1e9, cash_usd=1e9, position_cap_pct=1.0)
    assert (s.size_usd, s.max_loss_usd) == (120, 6)


def test_room_and_cash_limits(profiles):
    agg, _ = profiles
    s = size_position(profile=agg, tier=1, account_value=300, entry=100, stop=95, room_usd=50, cash_usd=300, position_cap_pct=1.0)
    assert (s.size_usd, s.max_loss_usd, s.limited_by) == (50, 2.5, "bucket_room")
    s = size_position(profile=agg, tier=1, account_value=300, entry=100, stop=95, room_usd=300, cash_usd=40, position_cap_pct=1.0)
    assert (s.size_usd, s.limited_by) == (40, "cash")
    s = size_position(profile=agg, tier=1, account_value=300, entry=100, stop=95, room_usd=0, cash_usd=300, position_cap_pct=1.0)
    assert (s.size_usd, s.limited_by) == (0, "bucket_room")   # the binding limit is always named


def test_long_term_has_no_stop(profiles):
    agg, _ = profiles
    s = size_position(profile=agg, tier=1, account_value=300, entry=500, stop=None, room_usd=75, cash_usd=300, position_cap_pct=1.0)
    assert (s.size_usd, s.limited_by) == (75, "bucket_room")


def test_bad_inputs(profiles):
    agg, _ = profiles
    with pytest.raises(ValueError):
        size_position(profile=agg, tier=1, account_value=300, entry=100, stop=101, room_usd=1, cash_usd=1, position_cap_pct=1.0)
    with pytest.raises(ValueError):
        size_position(profile=agg, tier=4, account_value=300, entry=100, stop=95, room_usd=1, cash_usd=1, position_cap_pct=1.0)


def test_bucket_room(profiles):
    agg, mod = profiles
    assert bucket_room(agg, "short_term", 300, 200) == pytest.approx(40)   # 80% of 300 = 240
    assert bucket_room(mod, "long_term", 300, 130) == 0                    # already over 40%


def test_drawdown_pause(profiles):
    agg, mod = profiles
    assert drawdown_paused(225, 300, agg)        # exactly -25%
    assert not drawdown_paused(226, 300, agg)
    assert drawdown_paused(255, 300, mod)        # exactly -15%
    assert not drawdown_paused(100, 0, agg)


def test_split_deposit(profiles):
    agg, mod = profiles
    assert split_deposit(300, 0, 0, agg) == {"long_term": 75, "short_term": 225}
    assert split_deposit(200, 100, 200, agg) == {"long_term": 25, "short_term": 175}    # total 500 -> 125 / 375
    assert split_deposit(100, 200, 100, agg) == {"long_term": 0, "short_term": 100}     # long-term overweight
    assert split_deposit(100, 0, 900, agg) == {"long_term": 100, "short_term": 0}       # long-term far below
    assert split_deposit(250, 300, 450, mod) == {"long_term": 50, "short_term": 200}    # total 1000 -> 350 / 650


def test_rank_by_profile(profiles):
    agg, mod = profiles
    ideas = [Idea("A", "S1", 1, 4, 0.010), Idea("B", "S2", 3, 2, 0.030), Idea("C", "S3", 2, 4, 0.020)]
    assert [i.symbol for i in rank(ideas, agg)] == ["B", "C", "A"]
    assert [i.symbol for i in rank(ideas, mod)] == ["C", "A", "B"]


def test_position_cap_25pct(profiles):
    agg, _ = profiles
    # risk alone would allow $180 on $300; the 25% cap holds it to $75 (loss at stop $3.75)
    s = size_position(profile=agg, tier=1, account_value=300, entry=100, stop=95, room_usd=1e9, cash_usd=1e9,
                      position_cap_pct=0.25)
    assert (s.size_usd, s.max_loss_usd, s.limited_by) == (75, 3.75, "position_cap")
    # a wide stop makes risk the tighter limit: 3% of 300 / 20% = $45
    s = size_position(profile=agg, tier=1, account_value=300, entry=100, stop=80, room_usd=1e9, cash_usd=1e9,
                      position_cap_pct=0.25)
    assert (s.size_usd, s.limited_by) == (45, "risk")
    with pytest.raises(ValueError):
        size_position(profile=agg, tier=1, account_value=300, entry=100, stop=95, room_usd=1, cash_usd=1,
                      position_cap_pct=0)


def test_planned_exit_skips_weekends_and_holidays():
    # Wed Nov 25 2026 + 3 sessions: Nov 25, (26 Thanksgiving closed) Nov 27, Nov 30
    assert planned_exit_day(date(2026, 11, 25), 3) == date(2026, 11, 30)
    assert planned_exit_day(date(2026, 11, 18), 1) == date(2026, 11, 18)


def test_earnings_block():
    kw = dict(enabled=True, entry_day=date(2026, 11, 18), max_hold_days=10)
    # 10 sessions from Nov 18 ends Dec 2 (Thanksgiving skipped)
    assert earnings_blocks_entry(is_etf=False, next_earnings=date(2026, 12, 2), **kw)[0]
    assert not earnings_blocks_entry(is_etf=False, next_earnings=date(2026, 12, 3), **kw)[0]
    blocked, why = earnings_blocks_entry(is_etf=False, next_earnings=None, **kw)
    assert blocked and "unknown" in why                      # fails closed
    assert not earnings_blocks_entry(is_etf=True, next_earnings=None, **kw)[0]
    assert not earnings_blocks_entry(is_etf=False, next_earnings=date(2026, 11, 20), enabled=False,
                                     entry_day=date(2026, 11, 18), max_hold_days=10)[0]


def test_size_rounds_down_to_the_cent(profiles):
    agg, _ = profiles
    s = size_position(profile=agg, tier=1, account_value=300, entry=100, stop=None, room_usd=1e9,
                      cash_usd=10.006, position_cap_pct=1.0)
    assert s.size_usd == 10.0 and s.size_usd <= 10.006
