from datetime import date

import pytest

from tradeagent import emailer, reports
from tradeagent.account import AccountState
from tradeagent.config import load_config
from tradeagent.papertrade import simulate_portfolio
from tradeagent.setups.library import LIBRARY
from tests.test_triggers import _walk

OFF = lambda *a: (_ for _ in ()).throw(RuntimeError("offline"))


def _state(cfg, plan=True):
    syms = ["SPY", "QQQ", "VTI", "SCHD", "IWM", "XLK", "XLF", "AAPL", "MSFT"]
    bars = {s: _walk(i, drift=0.0008) for i, s in enumerate(syms)}
    stats = {s.id: {"passes_evidence": True, "recommendable": True, "tier": 2, "mean_ret": 0.01, "edge": 3,
                    "confidence": 4, "n": 500, "loss_rate": 0.4, "tail_ret": -0.06} for s in LIBRARY}
    sim = simulate_portfolio(bars, cfg, stats, "2025-11-03", str(bars["SPY"].index[-1].date()), 300, 250, {},
                             plan_next_day=plan)
    return AccountState(bars["SPY"].index[-1].date(), sim, bars, {}, stats)


def test_digest_has_every_section_and_no_unsourced_numbers():
    cfg = load_config()
    st = _state(cfg)
    em = reports.digest(st, cfg, runner=OFF)
    assert emailer.evidence_check(em) == []
    titles = [s.title for s in em.sections]
    assert titles[0] == "Account" and any(t.startswith("Sells for") for t in titles) and "Buys for the next session" in titles
    assert em.subject.startswith("[SHADOW] Daily") and "$" in em.subject
    text = emailer.render_text(em, True)
    assert "Tier 1 (low risk)" in text and "cannot place trades" in text


def test_planning_only_happens_when_asked():
    cfg = load_config()
    assert _state(cfg, plan=False).sim.next_orders == []


def test_premarket_lists_actions():
    cfg = load_config()
    st = _state(cfg)
    em = reports.premarket(st, cfg)
    assert em.kind == "premarket" and emailer.evidence_check(em) == []
    assert em.subject.startswith("[SHADOW] Premarket")


def test_urgent_stop_hit_once_and_3_sigma():
    import pandas as pd
    from tradeagent.market import Quote
    cfg = load_config()
    st = _state(cfg)
    from tradeagent.papertrade import Position
    pos = Position("AAPL", "S2", "short_term", 1.0, 100.0, 95.0, 110.0, st.day, 20, sessions_held=3)
    st.sim.open_positions.append(pos)
    now = pd.Timestamp("2026-12-15 11:00", tz="America/New_York")
    q = {pos.symbol: Quote(pos.symbol, pos.stop * 0.99, pos.stop * 1.05, now.to_pydatetime())}
    em, keys = reports.urgent(st, q, cfg, sigmas={pos.symbol: 0.01}, now=now)
    assert em is not None and em.kind == "urgent" and emailer.evidence_check(em) == []
    assert any(k.startswith("stop:") for k in keys) and any(k.startswith("move:urgent") for k in keys)
    again, keys2 = reports.urgent(st, q, cfg, sigmas={pos.symbol: 0.01}, fired=set(keys), now=now)
    assert again is None and keys2 == []                                  # each event only once
    calm = {pos.symbol: Quote(pos.symbol, pos.stop * 1.10, pos.stop * 1.10, now.to_pydatetime())}
    assert reports.urgent(st, calm, cfg, sigmas={pos.symbol: 0.01}, now=now)[0] is None


def test_weekly_report_sections_and_sources():
    cfg = load_config()
    st = _state(cfg)
    em = reports.weekly(st, cfg)
    assert em.kind == "weekly" and emailer.evidence_check(em) == []
    titles = [s.title for s in em.sections]
    assert titles[0].startswith("Performance") and any(t.startswith("Fix needed") for t in titles)
    assert "Why things moved" in titles and "Recommendation scorecard" in titles


def test_twr_removes_deposits():
    import pandas as pd
    idx = pd.bdate_range("2026-01-05", periods=5)
    vals = pd.Series([100, 101, 351, 351, 355.1], index=idx, dtype=float)   # +250 deposit on day 3
    flows = pd.Series({idx[2]: 250.0})
    r = reports.twr(vals, flows, idx[1], idx[-1])
    assert r == pytest.approx((101 / 100) * (351 - 250) / 101 * 1 * 355.1 / 351 - 1, rel=1e-9)


def test_classify_expected_vs_decision():
    from types import SimpleNamespace as NS
    stats = {"S2": {"tail_ret": -0.063}}
    small = NS(setup_id="S2", entry=100, exit=95, reason="stop")
    big = NS(setup_id="S2", entry=100, exit=85, reason="stop")
    assert reports.classify(small, stats)[0] == "expected_variance"
    assert reports.classify(big, stats)[0] == "decision"
