from datetime import date, datetime

import pytest

from tradeagent import db, doctor, market_calendar, secrets
from tradeagent.market_calendar import NY


# --- market calendar -------------------------------------------------------

def test_thanksgiving_closed_and_day_after_is_half_day():
    assert market_calendar.session(date(2026, 11, 26)) is None
    friday = market_calendar.session(date(2026, 11, 27))
    assert friday.is_half_day and friday.close.hour == 13


def test_weekend_closed_and_normal_day_hours():
    assert not market_calendar.is_trading_day(date(2026, 11, 21))
    s = market_calendar.session(date(2026, 11, 18))
    assert (s.open.hour, s.open.minute, s.close.hour) == (9, 30, 16)
    assert not s.is_half_day


def test_next_session_skips_holiday():
    assert market_calendar.next_session(date(2026, 11, 25)).day == date(2026, 11, 27)


def test_market_open_at():
    assert market_calendar.market_open_at(datetime(2026, 11, 18, 10, 0, tzinfo=NY))
    assert not market_calendar.market_open_at(datetime(2026, 11, 18, 16, 0, tzinfo=NY))
    assert not market_calendar.market_open_at(datetime(2026, 11, 27, 13, 30, tzinfo=NY))
    with pytest.raises(ValueError):
        market_calendar.market_open_at(datetime(2026, 11, 18, 10, 0))


# --- secrets ---------------------------------------------------------------

def test_secrets_roundtrip_in_fake_keychain(memory_keyring):
    assert not secrets.has_secret("gmail_app_password")
    secrets.set_secret("gmail_app_password", "abcd")
    assert secrets.get_secret("gmail_app_password") == "abcd"
    assert ("trading-agent", "gmail_app_password") in memory_keyring.store


def test_secrets_reject_unknown_and_empty():
    with pytest.raises(KeyError):
        secrets.get_secret("bank_password")
    with pytest.raises(ValueError):
        secrets.set_secret("gmail_app_password", "")


# --- database --------------------------------------------------------------

def test_init_db_is_idempotent_and_latch_is_one_way(tmp_path):
    path = tmp_path / "agent.db"
    db.init_db(path)
    db.init_db(path)
    with db.connect(path) as conn:
        assert db.get_meta(conn, "schema_version") == str(db.SCHEMA_VERSION)
        assert not db.ever_reached_switch(conn)
        db.mark_reached_switch(conn)
    db.init_db(path)  # re-running init must not reset the latch
    with db.connect(path) as conn:
        assert db.ever_reached_switch(conn)


def test_schema_rejects_bad_values(tmp_path):
    import sqlite3
    path = db.init_db(tmp_path / "agent.db")
    with db.connect(path) as conn, pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO recommendations(created_at, profile, symbol, action, bucket, tier, stars, setup_id, "
            "size_usd, max_loss_usd, evidence) VALUES ('t','aggressive','X','short','short_term',1,3,'s',1,1,'{}')"
        )


# --- doctor ----------------------------------------------------------------

def test_doctor_reports_without_failing_on_missing_phase_items(project, tmp_path):
    checks = doctor.run_checks(root=project, db_path=tmp_path / "agent.db", today=date(2026, 11, 25))
    by_name = {c.name: c for c in checks}
    assert by_name["Config"].status == "ok"
    assert by_name["Database"].status == "ok"
    assert by_name["Risk profile"].detail.startswith("moderate: 2%")
    assert "Fri Nov 27" in by_name["Market calendar"].detail and "half day" in by_name["Market calendar"].detail
    assert by_name["Keychain: gmail_app_password"].status == "warn"
    assert by_name["Email addresses"].status == "warn"
    assert "Keychain: finnhub_api_key" not in by_name          # Finnhub not in use
    assert by_name["Market data"].status == "warn" and "yahoo only" in by_name["Market data"].detail
    report = doctor.format_report(checks)
    assert "failing" in report


def test_doctor_fails_on_invalid_config(project, tmp_path):
    (project / "config.yaml").write_text("version: 2\n")
    checks = doctor.run_checks(root=project, db_path=tmp_path / "agent.db")
    assert checks[-1].name == "Config" and checks[-1].status == "fail"


def test_doctor_asks_for_finnhub_key_when_crosscheck_on(project, tmp_path):
    cfg = (project / "config.yaml").read_text().replace("crosscheck: null", "crosscheck: finnhub")
    (project / "config.yaml").write_text(cfg)
    by_name = {c.name: c for c in doctor.run_checks(root=project, db_path=tmp_path / "agent.db")}
    assert by_name["Keychain: finnhub_api_key"].status == "warn"
    assert by_name["Market data"].status == "ok"
