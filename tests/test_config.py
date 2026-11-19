import pytest
import yaml
from pydantic import ValidationError

from tradeagent.config import active_profile, active_profile_name, load_config, reached_switch


def _write(project, mutate):
    data = yaml.safe_load((project / "config.yaml").read_text())
    mutate(data)
    (project / "config.yaml").write_text(yaml.safe_dump(data))


def test_repo_config_is_valid(project):
    config = load_config(project)
    assert config.mode == "shadow"
    assert config.account.allow_orders is False
    assert config.local.email.to == "you@example.com"


def test_approved_numbers(project):
    c = load_config(project)
    agg, mod = c.profiles.aggressive, c.profiles.moderate
    assert (agg.max_loss_per_trade, agg.tier3_max_loss_per_trade, agg.drawdown_pause) == (0.03, 0.015, 0.25)
    assert (mod.max_loss_per_trade, mod.tier3_max_loss_per_trade, mod.drawdown_pause) == (0.02, 0.01, 0.15)
    assert (agg.buckets.long_term.min, agg.buckets.long_term.max, agg.buckets.long_term.target) == (0.35, 0.45, 0.40)
    assert c.profiles.start_profile == "moderate"
    assert (c.cash.park_idle_in, c.cash.min_park_usd) == ("BIL", 20)
    assert (c.setup_switch.enabled, c.setup_switch.last_n_trades, c.setup_switch.min_avg_r) == (True, 20, 0.0)
    assert mod.buckets == agg.buckets   # same split in both phases
    assert agg.rank_by == "expected_return" and mod.rank_by == "stars"
    assert c.profiles.switch_to_moderate_at == 1000
    assert (c.tiers.tier1.max_loss_rate, c.tiers.tier1.max_tail_loss) == (0.25, 0.08)
    assert (c.tiers.tier2.max_loss_rate, c.tiers.tier2.max_tail_loss) == (0.40, 0.15)
    assert c.evidence.min_trades == 30
    assert c.evidence.min_edge == 2
    assert (c.positions.max_position_pct, c.positions.min_position_usd) == (0.25, 20)


def test_market_data_sources(project):
    c = load_config(project)
    assert (c.market_data.primary, c.market_data.crosscheck) == ("yahoo", None)


def test_crosscheck_must_differ_from_primary(project):
    _write(project, lambda d: d["market_data"].__setitem__("crosscheck", "yahoo"))
    with pytest.raises(ValidationError, match="different source"):
        load_config(project)


def test_orders_can_never_be_enabled(project):
    _write(project, lambda d: d["account"].__setitem__("allow_orders", True))
    with pytest.raises(ValidationError, match="never places trades"):
        load_config(project)


def test_bucket_targets_must_sum_to_one(project):
    _write(project, lambda d: d["profiles"]["moderate"]["buckets"]["long_term"].__setitem__("target", 0.44))  # in band, sum 1.04
    with pytest.raises(ValidationError, match="add up to 1"):
        load_config(project)


def test_target_must_sit_in_band(project):
    def mutate(d):
        b = d["profiles"]["aggressive"]["buckets"]
        b["long_term"]["target"], b["short_term"]["target"] = 0.30, 0.70
    _write(project, mutate)
    with pytest.raises(ValidationError, match="outside its band"):
        load_config(project)


def test_tier3_cap_cannot_exceed_trade_cap(project):
    _write(project, lambda d: d["profiles"]["moderate"].__setitem__("tier3_max_loss_per_trade", 0.05))
    with pytest.raises(ValidationError, match="tier3"):
        load_config(project)


def test_tier1_must_be_stricter(project):
    _write(project, lambda d: d["tiers"]["tier1"].__setitem__("max_loss_rate", 0.5))
    with pytest.raises(ValidationError, match="strict"):
        load_config(project)


def test_unknown_keys_rejected(project):
    _write(project, lambda d: d.__setitem__("typo_key", 1))
    with pytest.raises(ValidationError):
        load_config(project)


def test_profile_switch_is_one_way(project):
    c = load_config(project)
    # moderate from the start: the $1,000 switch never matters
    assert active_profile_name(c, ever_reached_switch=False) == "moderate"
    assert active_profile(c, ever_reached_switch=False).max_loss_per_trade == 0.02
    # with an aggressive start, the switch is one-way at $1,000
    _write(project, lambda d: d["profiles"].__setitem__("start_profile", "aggressive"))
    c = load_config(project)
    assert not reached_switch(c, 999.99) and reached_switch(c, 1000)
    assert active_profile_name(c, ever_reached_switch=False) == "aggressive"
    assert active_profile_name(c, ever_reached_switch=True) == "moderate"


def test_paper_watch_never_overlaps_traded_list(project):
    from tradeagent.setups.library import STOCKS
    c = load_config(project)
    assert len(c.paper_watch.stocks) == 37 and c.paper_watch.review_after_trades == 30
    assert not set(c.paper_watch.stocks) & set(STOCKS)
