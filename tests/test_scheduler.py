from datetime import datetime
from zoneinfo import ZoneInfo

from tradeagent import scheduler
from tradeagent.config import load_config

NY = ZoneInfo("America/New_York")


def at(y, m, d, hh, mm):
    return datetime(y, m, d, hh, mm, tzinfo=NY)


def test_due_by_new_york_time():
    cfg = load_config()
    assert scheduler.due(cfg, at(2026, 11, 18, 8, 15), set()) == ["premarket"]
    assert scheduler.due(cfg, at(2026, 11, 18, 11, 0), set()) == ["intraday"]
    assert scheduler.due(cfg, at(2026, 11, 18, 16, 45), set()) == ["close"]
    assert scheduler.due(cfg, at(2026, 11, 18, 16, 45), {"close"}) == []           # once a day
    assert scheduler.due(cfg, at(2026, 11, 21, 9, 30), set()) == ["weekly"]         # Saturday
    assert scheduler.due(cfg, at(2026, 11, 26, 11, 0), set()) == []                  # Thanksgiving: closed
    assert scheduler.due(cfg, at(2026, 11, 27, 14, 0), set()) == []                  # half day closes 13:00
    # a Mac set to another time zone still follows New York
    tokyo = datetime(2026, 11, 19, 1, 0, tzinfo=ZoneInfo("Asia/Tokyo"))             # = Nov 18 11:00 New York
    assert scheduler.due(cfg, tokyo, set()) == ["intraday"]


def test_launchd_plist_runs_every_15_minutes(tmp_path):
    xml = scheduler.launchd_plist("/usr/local/bin/uv", tmp_path, "/usr/bin:/bin")
    assert "<integer>900</integer>" in xml and "<string>tick</string>" in xml and str(tmp_path) in xml


def _not_started_db(monkeypatch, tmp_path):
    """run_kind on a temp database, with the shadow run not started yet: it ends 'quiet' before fetching anything."""
    from tradeagent import account, db
    path = tmp_path / "t.db"
    real_init, real_connect = db.init_db, db.connect
    monkeypatch.setattr(db, "init_db", lambda p=None: real_init(path))
    monkeypatch.setattr(db, "connect", lambda p=None: real_connect(path))

    def not_started(*a, **k):
        raise account.NotStarted("shadow run not started")
    monkeypatch.setattr(account, "build", not_started)
    return lambda: real_connect(path)


def test_a_dry_run_does_not_count_as_the_days_real_run(monkeypatch, tmp_path):
    cfg, open_db = load_config(), _not_started_db(monkeypatch, tmp_path)
    early, eight = at(2026, 11, 23, 7, 0), at(2026, 11, 23, 8, 0)
    scheduler.run_kind("premarket", cfg, now=early, dry_run=True)
    conn = open_db()
    assert "premarket" not in scheduler._done_today(conn, early)
    assert scheduler.due(cfg, eight, scheduler._done_today(conn, eight)) == ["premarket"]   # 08:00 still runs
    row = conn.execute("SELECT kind, status, detail FROM runs").fetchone()
    assert (row["kind"], row["status"]) == ("manual", "quiet") and row["detail"].startswith("dry run of premarket: ")
    assert scheduler._system_lines(conn, early)[0].text.startswith("Runs today: 0 OK, 0 errors")
    scheduler.run_kind("premarket", cfg, now=eight)                                          # the real run counts
    assert "premarket" in scheduler._done_today(conn, eight)
    assert scheduler.due(cfg, at(2026, 11, 23, 8, 15), scheduler._done_today(conn, eight)) == []
