from datetime import date

import numpy as np
import pandas as pd
import pytest

from tradeagent import triggers as tg
from tradeagent.config import load_config
from tradeagent.papertrade import simulate_portfolio
from tradeagent.setups.library import LIBRARY

D = date(2026, 11, 18)


@pytest.fixture(scope="module")
def cfg():
    return load_config()


def test_move_thresholds(cfg):
    assert tg.move("X", 101.9, 100, 0.01, D, cfg) is None                     # 1.9σ
    e = tg.move("X", 102.5, 100, 0.01, D, cfg)
    assert e and not e.urgent and e.when == "now"                              # 2.5σ
    e = tg.move("X", 96.9, 100, 0.01, D, cfg)
    assert e and e.urgent and e.detail["sigmas"] == pytest.approx(-3.1)        # -3.1σ
    assert tg.move("X", 120, 100, None, D, cfg) is None                         # no sigma yet


def test_daily_sigma_needs_full_lookback():
    closes = pd.Series(100 * np.cumprod(1 + np.r_[0, np.tile([0.01, -0.01], 40)]))
    assert tg.daily_sigma(closes, 60) == pytest.approx(0.01, rel=0.05)
    assert tg.daily_sigma(closes.head(30), 60) is None


def test_stop_and_target():
    assert tg.stop_or_target("X", 94.9, 95, 110, D).rule == "stop_hit"
    assert tg.stop_or_target("X", 110, 95, 110, D).rule == "target_hit"
    assert tg.stop_or_target("X", 100, 95, 110, D) is None
    assert tg.stop_or_target("SPY", 1, None, None, D) is None                  # long-term: never


def test_bucket_drift_fires_once_per_episode(cfg):
    agg = cfg.profiles.aggressive
    state = {}
    (e,) = tg.bucket_drift(10, 90, agg, D, state)                              # long-term 10% < 35%: one alert, not two
    assert e.detail["long_term_share"] == 0.1
    assert tg.bucket_drift(11, 89, agg, D, state) == []                        # still out: silent
    assert tg.bucket_drift(40, 60, agg, D, state) == []                        # back in band (35-45%)
    assert len(tg.bucket_drift(50, 50, agg, D, state)) == 1                    # new episode


def test_drawdown_fires_once(cfg):
    agg = cfg.profiles.aggressive
    assert tg.drawdown(225, 300, agg, already_paused=False).urgent
    assert tg.drawdown(200, 300, agg, already_paused=True) is None
    assert tg.drawdown(260, 300, agg, already_paused=False) is None


def test_deposits_and_items_skip_seen():
    tx = [{"id": 1, "date": "2026-11-02", "type": "deposit", "amount": 250},
          {"id": 2, "date": "2026-11-03", "type": "buy", "amount": 100},
          {"id": 3, "date": "2026-12-01", "type": "deposit", "amount": 200}]
    assert [e.detail["amount"] for e in tg.deposits(tx, {"1"})] == [200]
    items = [{"id": "a", "title": "x"}, {"id": "b", "title": "y"}]
    ev = tg.new_items("headline", "AAPL", items, {"a"})
    assert len(ev) == 1 and ev[0].when == "close" and not ev[0].urgent


def test_earnings_soon(cfg):
    assert tg.earnings_soon("X", date(2026, 11, 20), 2, cfg)
    assert tg.earnings_soon("X", date(2026, 11, 30), 5, cfg) is None
    assert tg.earnings_soon("X", None, None, cfg) is None


def test_dedupe():
    a = tg.Event("move", "X", False, "now", "k1")
    b = tg.Event("move", "X", False, "now", "k1")
    c = tg.Event("move", "Y", False, "now", "k2")
    assert tg.dedupe([a, b, c], {"k2"}) == [a]


# --- hypothetical portfolio invariants ------------------------------------------

def _walk(seed, n=520, drift=0.0004, vol=0.012):
    rng = np.random.default_rng(seed)
    close = 100 * np.cumprod(1 + rng.normal(drift, vol, n))
    open_ = close * (1 + rng.normal(0, 0.003, n))
    high = np.maximum(open_, close) * (1 + abs(rng.normal(0, 0.004, n)))
    low = np.minimum(open_, close) * (1 - abs(rng.normal(0, 0.004, n)))
    idx = pd.bdate_range("2025-01-02", periods=n)
    return pd.DataFrame({"open": open_, "high": high, "low": low, "close": close,
                         "volume": rng.integers(1_000_000, 3_000_000, n).astype(float)}, index=idx)


def test_portfolio_invariants(cfg):
    syms = ["SPY", "QQQ", "VTI", "SCHD", "IWM", "XLK", "AAPL", "MSFT"]
    bars = {s: _walk(i) for i, s in enumerate(syms)}
    stats = {s.id: {"passes_evidence": True, "tier": 2, "mean_ret": 0.01 * (k + 1)} for k, s in enumerate(LIBRARY)}
    earnings = {"AAPL": [date(2026, 1, 29)], "MSFT": [date(2026, 1, 28)]}
    start, end = "2025-11-03", str(bars["SPY"].index[-1].date())
    sim = simulate_portfolio(bars, cfg, stats, start, end, 300, 250, earnings)
    d = sim.daily
    assert (d[["cash_lt", "cash_st"]] >= -1e-6).all().all()                    # never spends money it doesn't have
    months = d.index.to_period("M").nunique()
    assert len(sim.deposits) == months                                        # start + one per later month
    for day, amount, split in sim.deposits:
        assert split["long_term"] + split["short_term"] == pytest.approx(amount)
    for t in sim.trades:                                                       # 25% cap at entry
        prior = d.loc[:t.entry_day, "value"].iloc[-2] if len(d.loc[:t.entry_day]) > 1 else 300
        assert t.dollars_in <= 0.25 * prior + 0.01
    assert all(p.stop is None for p in sim.open_positions if p.bucket == "long_term")
    assert all(t.dollars_in >= 20 * (1 - 0.0005) - 0.01 for t in sim.trades)  # $20 minimum (less entry cost)
    assert all(p.qty * p.entry >= 20 * (1 - 0.0005) - 0.01 for p in sim.open_positions)


def test_low_edge_setup_never_traded(cfg):
    syms = ["SPY", "QQQ", "VTI", "SCHD", "IWM", "XLK", "AAPL", "MSFT"]
    bars = {s: _walk(i) for i, s in enumerate(syms)}
    stats = {s.id: {"passes_evidence": True, "recommendable": s.id != "S1", "tier": 2, "mean_ret": 0.01,
                    "edge": 1 if s.id == "S1" else 3, "confidence": 3} for s in LIBRARY}
    sim = simulate_portfolio(bars, cfg, stats, "2025-11-03", str(bars["SPY"].index[-1].date()), 300, 250,
                             {"AAPL": [date(2026, 1, 29)], "MSFT": [date(2026, 1, 28)]})
    assert all(t.setup_id != "S1" for t in sim.trades)
    assert all(p.setup_id != "S1" for p in sim.open_positions)


def test_long_term_spreads_across_core_etfs(cfg):
    """'Buy whichever is held least' must count every lot, so no ETF ends far above the others."""
    from tradeagent.setups.library import CORE_ETFS
    syms = ["SPY", "QQQ", "VTI", "SCHD"]
    bars = {s: _walk(i, drift=0.0, vol=0.002) for i, s in enumerate(syms)}  # flat prices: lots compare fairly
    stats = {s.id: {"passes_evidence": True, "recommendable": s.kind == "accumulate", "tier": 2, "mean_ret": 0.01,
                    "edge": 3, "confidence": 2} for s in LIBRARY}
    sim = simulate_portfolio(bars, cfg, stats, "2025-06-02", str(bars["SPY"].index[-1].date()), 300, 250, {})
    held = {s: 0.0 for s in CORE_ETFS}
    for p in sim.open_positions:
        held[p.symbol] += p.qty * p.entry
    assert min(held.values()) > 0
    assert max(held.values()) / min(held.values()) < 2.0


def test_long_term_funded_only_by_deposits(cfg):
    """Long-term cash may rise only on deposit days, and by exactly the deposit's long-term share."""
    syms = ["SPY", "QQQ", "VTI", "SCHD", "IWM", "XLK", "AAPL", "MSFT"]
    bars = {s: _walk(i) for i, s in enumerate(syms)}
    stats = {s.id: {"passes_evidence": True, "tier": 2, "mean_ret": 0.01 * (k + 1)} for k, s in enumerate(LIBRARY)}
    sim = simulate_portfolio(bars, cfg, stats, "2025-11-03", str(bars["SPY"].index[-1].date()), 300, 250,
                             {"AAPL": [date(2026, 1, 29)], "MSFT": [date(2026, 1, 28)]})
    assert any(t.bucket == "short_term" for t in sim.trades)            # short-term trades did close
    lt_in = {day: split["long_term"] for day, _, split in sim.deposits}
    lt_cash = sim.daily["cash_lt"]
    prev = 0.0
    for day, now in lt_cash.items():
        if now > prev + 1e-6:                                             # long-term cash went up...
            assert day in lt_in and now - prev <= lt_in[day] + 1e-6       # ...only by a deposit's share
        prev = now


def test_goal_rules_wrapper_matches_plain_run_when_restart_off(cfg):
    from tradeagent.papertrade import simulate_with_goal_rules
    syms = ["SPY", "QQQ", "VTI", "SCHD", "IWM", "XLK", "AAPL", "MSFT"]
    bars = {s: _walk(i) for i, s in enumerate(syms)}
    stats = {s.id: {"passes_evidence": True, "tier": 2, "mean_ret": 0.01 * (k + 1)} for k, s in enumerate(LIBRARY)}
    args = (bars, cfg, stats, "2025-11-03", str(bars["SPY"].index[-1].date()), 300, 250, {})
    off = cfg.model_copy(update={"goal": cfg.goal.model_copy(update={"restart_when_paper_book_recovers": False}),
                                 "setup_switch": cfg.setup_switch.model_copy(update={"enabled": False})})
    plain = simulate_portfolio(*((bars, off) + args[2:]))
    wrapped = simulate_with_goal_rules(*((bars, off) + args[2:]))
    assert plain.daily["value"].iloc[-1] == pytest.approx(wrapped.daily["value"].iloc[-1])
    on = simulate_with_goal_rules(*args)                      # restart on: runs, never spends money it lacks
    assert (on.daily[["cash_lt", "cash_st"]] >= -1e-6).all().all()


def test_config_restart_rule_on(cfg):
    assert cfg.goal.restart_when_paper_book_recovers and cfg.goal.restart_needs_approval


def test_idle_cash_earns_parking_return(cfg):
    from tradeagent.papertrade import simulate_with_goal_rules
    syms = ["SPY", "QQQ", "VTI", "SCHD", "IWM", "XLK"]
    bars = {s: _walk(i) for i, s in enumerate(syms)}
    idx = bars["SPY"].index
    bars["BIL"] = pd.DataFrame({c: 100 * (1.0002 ** np.arange(len(idx))) for c in ("open", "high", "low", "close")}
                               | {"volume": 1e6}, index=idx)                     # steady +0.02%/day
    stats = {s.id: {"passes_evidence": True, "recommendable": False, "tier": 2, "mean_ret": 0.01} for s in LIBRARY}
    off = cfg.model_copy(update={"cash": cfg.cash.model_copy(update={"park_idle_in": None})})
    args = (stats, "2025-11-03", str(idx[-1].date()), 300, 250, {})
    plain = simulate_with_goal_rules(bars, off, *args)
    parked = simulate_with_goal_rules(bars, cfg, *args)
    assert parked.daily["value"].iloc[-1] > plain.daily["value"].iloc[-1]   # no trades: only cash yield differs


def test_setup_switch_skips_a_losing_setup(cfg):
    """A setup whose last N paper trades average below zero is skipped; with the switch off it trades."""
    syms = ["SPY", "QQQ", "VTI", "SCHD", "IWM", "XLK", "AAPL", "MSFT"]
    bars = {s: _walk(i) for i, s in enumerate(syms)}
    stats = {s.id: {"passes_evidence": True, "tier": 2, "mean_ret": 0.01} for s in LIBRARY}
    end = str(bars["SPY"].index[-1].date())
    strict = simulate_portfolio(bars, cfg, stats, "2025-11-03", end, 300, 250, {}, setup_switch_n=5,
                                setup_switch_min_r=99.0)       # impossible bar: every setup is switched off
    loose = simulate_portfolio(bars, cfg, stats, "2025-11-03", end, 300, 250, {})
    n_strict = len([t for t in strict.trades if t.bucket == "short_term"])
    n_loose = len([t for t in loose.trades if t.bucket == "short_term"])
    assert any("switched off" in k for k in strict.blocked)
    assert n_strict < n_loose      # trades only before a setup has N closed paper trades to judge


def test_paper_watch_compares_groups(cfg):
    from tradeagent import paperwatch
    syms = list(cfg.paper_watch.stocks[:3]) + ["AAPL", "MSFT"]
    bars = {s: _walk(i, n=700, drift=0.001) for i, s in enumerate(syms)}
    stats = paperwatch.compare(bars, cfg, "2025-01-01")
    groups = {(g.setup_id, g.group) for g in stats}
    assert groups == {("S2", "watched"), ("S2", "traded"), ("S4", "watched"), ("S4", "traded")}
    md = paperwatch.to_markdown(stats, "2025-01-01", cfg)
    assert "never recommended" in md and "Review rule" in md
