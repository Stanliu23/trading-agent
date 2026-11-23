import json
from datetime import datetime

import pytest

from tradeagent import db, trials
from tradeagent.config import load_config


@pytest.fixture
def conn(tmp_path):
    return db.connect(db.init_db(tmp_path / "t.db"))


def _ledger(tmp_path, status="trial"):
    p = tmp_path / "ledger.json"
    p.write_text(json.dumps({"ideas": [{"id": "X1", "title": "Test idea", "status": status, "where": "backtest",
                                        "trial_start": "2026-12-01"}]}))
    return p


def _cfg(on=True):
    return load_config().model_copy(update={"trials": {"X1": on}})


def test_real_ledger_has_the_two_proposals_with_rules_fixed():
    ideas = {i["id"]: i for i in trials.ledger()}
    assert {"2026-11-23-1", "2026-11-23-2", "2026-11-23-3"} <= set(ideas)
    for i in ideas.values():
        assert i["status"] in ("proposed", "approved") and i["backtest_rule"] and i["removal_rule"] and i["where"]


def test_proposed_ideas_wait_for_approval(conn, tmp_path):
    lines = trials.weekly_lines(conn, {}, _cfg(), datetime(2026, 11, 28), path=_ledger(tmp_path, "proposed"))
    assert "waiting for your approval" in lines[0].text and "Where: backtest" in lines[0].text


def test_a_failing_trial_is_removed_by_its_own_rule_and_stays_removed(conn, tmp_path):
    p, cfg = _ledger(tmp_path), _cfg()
    assert trials.is_active(cfg, conn, "X1")
    bad = {"X1": lambda *a: trials.Outcome("remove", "new rule -0.30R per trade vs old, 90% range below 0")}
    lines = trials.weekly_lines(conn, {}, cfg, datetime(2026, 12, 19), path=p, checks=bad)
    assert "REMOVED today" in lines[0].text and not trials.is_active(cfg, conn, "X1")
    good = {"X1": lambda *a: trials.Outcome("keep_watching", "fine")}
    again = trials.weekly_lines(conn, {}, cfg, datetime(2026, 12, 26), path=p, checks=good)
    assert "REMOVED on 2026-12-19" in again[0].text and not trials.is_active(cfg, conn, "X1")


def test_dry_run_never_removes(conn, tmp_path):
    bad = {"X1": lambda *a: trials.Outcome("remove", "worse")}
    lines = trials.weekly_lines(conn, {}, _cfg(), datetime(2026, 12, 19), save=False, path=_ledger(tmp_path), checks=bad)
    assert "would be removed" in lines[0].text and trials.is_active(_cfg(), conn, "X1")


def test_trial_without_a_check_or_switched_off_is_flagged(conn, tmp_path):
    p = _ledger(tmp_path)
    assert "check is not built" in trials.weekly_lines(conn, {}, _cfg(), datetime(2026, 12, 5), path=p, checks={})[0].text
    off = trials.weekly_lines(conn, {}, _cfg(False), datetime(2026, 12, 5), path=p, checks={})
    assert "switched off in config" in off[0].text and not trials.is_active(_cfg(False), conn, "X1")


def test_nothing_is_on_trial_today():
    assert load_config().trials == {}
