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
