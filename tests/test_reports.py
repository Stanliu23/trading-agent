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
