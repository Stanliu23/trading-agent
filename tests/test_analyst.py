from datetime import datetime

import pytest

from tradeagent import analyst, db
from tradeagent.analyst import Fact
from tradeagent.config import load_config

FACTS = [Fact("f1", "AAAA closed at $84.20, a 52-week high, on 1.9x its 50-day average volume.", "prices 11-18"),
         Fact("f2", "741 past S2 trades: 50% positive, average +0.98%.", "setup S2"),
         Fact("f3", "Earnings filings for AAAA moved it a median +2.1% vs SPY over 5 days (14 events).", "SEC 8-K")]
NOW = datetime(2026, 11, 19, 16, 30).astimezone()


@pytest.fixture
def conn(tmp_path):
    return db.connect(db.init_db(tmp_path / "a.db"))


@pytest.fixture
def cfg():
    return load_config()


def runner_returning(payload):
    def run(system, prompt, schema, config):
        assert "[f1]" in prompt and "Use ONLY the facts" in system
        return payload
    return run


def test_good_ai_lines_are_kept_with_sources(cfg, conn):
    out = {"why_now": {"text": "AAAA closed at a 52-week high of $84.20 on 1.9x normal volume.", "facts": ["f1"]},
           "lines": [{"text": "Similar breakouts were positive 50% of the time, averaging +0.98%.", "facts": ["f2"]}]}
    w = analyst.write("BUY AAAA", FACTS, cfg, conn=conn, runner=runner_returning(out), now=NOW)
    assert w.used_ai and w.why_now.source == "prices 11-18" and w.lines[0].source == "setup S2" and w.dropped == []


def test_invented_number_is_dropped(cfg, conn):
    out = {"why_now": {"text": "AAAA closed at $84.20, a 52-week high.", "facts": ["f1"]},
           "lines": [{"text": "Analysts expect 15% upside.", "facts": ["f2"]},                        # 15 not in f2
                     {"text": "Earnings moved it +2.1% over 5 days.", "facts": ["f9"]}]}             # unknown fact
    w = analyst.write("BUY AAAA", FACTS, cfg, conn=conn, runner=runner_returning(out), now=NOW)
    assert w.lines == [] and len(w.dropped) == 2
    assert "numbers not in cited facts" in w.dropped[0] and "unknown fact" in w.dropped[1]


def test_bad_why_now_falls_back_to_template(cfg, conn):
    out = {"why_now": {"text": "AAAA jumped 7% today.", "facts": ["f1"]}, "lines": []}
    w = analyst.write("BUY AAAA", FACTS, cfg, conn=conn, runner=runner_returning(out), now=NOW)
    assert w.why_now.text == FACTS[0].text and not w.used_ai


def test_ai_failure_and_cap_use_template(cfg, conn):
    def boom(*a):
        raise RuntimeError("OAuth session expired")
    w = analyst.write("BUY AAAA", FACTS, cfg, conn=conn, runner=boom, now=NOW)
    assert w.why_now.text == FACTS[0].text and len(w.lines) == 2
    good = {"why_now": {"text": "AAAA closed at $84.20, a 52-week high.", "facts": ["f1"]}, "lines": []}
    for _ in range(cfg.ai.max_runs_per_day):
        analyst.write("x", FACTS, cfg, conn=conn, runner=lambda *a: good, now=NOW)   # real AI runs count
    called = []
    w = analyst.write("x", FACTS, cfg, conn=conn, runner=lambda *a: called.append(1) or {}, now=NOW)
    assert called == [] and not w.used_ai                       # capped: the AI is not called at all


def test_template_output_passes_email_evidence_check():
    from tradeagent.emailer import Email, Footer, Section, evidence_check
    w = analyst.template(FACTS)
    em = Email("digest", "Daily", w.why_now, [Section("Why", w.lines)], Footer("now", None, "x"))
    assert evidence_check(em) == []


def test_number_matching_handles_formats():
    f = {"a": Fact("a", "Value $1,234.50, down −3.0% (12 events).", "s")}
    assert analyst.check("It fell -3% to $1234.5 over 12 events.", ["a"], f) is None
    assert analyst.check("It fell 4%.", ["a"], f) is not None


def test_trailing_zero_numbers_are_not_confused():
    f = {"a": Fact("a", "It rose 1% on 100 shares.", "s")}
    assert analyst.check("It rose 10%.", ["a"], f) is not None      # 10 is not 1
    assert analyst.check("It rose 1.0% on 100 shares.", ["a"], f) is None
    assert analyst.check("It rose 1% on 10 shares.", ["a"], f) is not None


def test_failed_calls_do_not_use_up_the_cap(cfg, conn):
    def boom(*a):
        raise RuntimeError("not signed in")
    for _ in range(cfg.ai.max_runs_per_day + 3):
        analyst.write("x", FACTS, cfg, conn=conn, runner=boom, now=NOW)
    called = []
    good = {"why_now": {"text": "AAAA closed at $84.20, a 52-week high.", "facts": ["f1"]}, "lines": []}
    w = analyst.write("x", FACTS, cfg, conn=conn, runner=lambda *a: called.append(1) or good, now=NOW)
    assert called == [1] and w.used_ai


def test_old_database_is_migrated(tmp_path):
    import sqlite3
    p = tmp_path / "old.db"
    with sqlite3.connect(p) as c:
        c.execute("CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        c.execute("INSERT INTO meta VALUES ('schema_version','1')")
        c.execute("CREATE TABLE ai_runs(id INTEGER PRIMARY KEY, run_at TEXT, purpose TEXT, status TEXT CHECK (status IN ('ok','fallback')))")
    db.init_db(p)
    with db.connect(p) as c:
        c.execute("INSERT INTO ai_runs(run_at, purpose, status) VALUES ('2026-11-19','x','rejected')")   # new value accepted
        assert db.get_meta(c, "schema_version") == "2"


def test_lines_restating_the_card_are_skipped(cfg, conn):
    out = {"why_now": {"text": "AAAA closed at $84.20, a 52-week high.", "facts": ["f1"]},
           "lines": [{"text": "741 past trades, 50% positive.", "facts": ["f2"]},
                     {"text": "Earnings moved it +2.1% over 5 days in 14 events.", "facts": ["f3"]}]}
    w = analyst.write("BUY", FACTS, cfg, conn=conn, runner=runner_returning(out), now=NOW, already_shown=frozenset({"f2"}))
    assert [l.text for l in w.lines] == ["Earnings moved it +2.1% over 5 days in 14 events."]
    t = analyst.template(FACTS, frozenset({"f2"}))
    assert [l.text for l in t.lines] == [FACTS[2].text]
