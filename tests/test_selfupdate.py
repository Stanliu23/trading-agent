import subprocess
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from tradeagent import db, selfupdate

NY = ZoneInfo("America/New_York")


@pytest.fixture
def conn(tmp_path):
    return db.connect(db.init_db(tmp_path / "u.db"))


def fake_git(state):
    def run(cmd, **kw):
        state["calls"].append(cmd)
        args = cmd[3:] if cmd[0] == "git" else cmd
        out = ""
        if args[:2] == ["rev-parse", "HEAD"]:
            out = state["head"]
        elif args[:2] == ["rev-parse", "origin/main"]:
            out = state["remote"]
        elif args[:1] == ["status"]:
            out = state.get("dirty", "")
        elif args[:2] == ["diff", "--name-only"]:
            out = "\n".join(state["changed"])
        elif args[:1] == ["log"]:
            out = "abc123 New rules"
        return subprocess.CompletedProcess(cmd, 0, out, "")
    return run


def test_never_during_market_hours(conn, tmp_path):
    (tmp_path / ".git").mkdir()
    st = {"calls": [], "head": "a", "remote": "b", "changed": []}
    noon = datetime(2026, 11, 20, 12, 0, tzinfo=NY)                     # a Friday session
    assert selfupdate.maybe_update(conn, noon, root=tmp_path, run=fake_git(st)) is None and st["calls"] == []


def test_pulls_and_rebuilds_when_setups_change(conn, tmp_path):
    (tmp_path / ".git").mkdir()
    st = {"calls": [], "head": "a", "remote": "b", "changed": ["src/tradeagent/setups/library.py", "uv.lock"]}
    evening = datetime(2026, 11, 20, 19, 0, tzinfo=NY)
    msg = selfupdate.maybe_update(conn, evening, root=tmp_path, run=fake_git(st))
    assert "abc123" in msg and "packages updated" in msg and "setup statistics rebuilt" in msg
    assert any(c[3:5] == ["merge", "--ff-only"] for c in st["calls"] if c[0] == "git")
    assert not any("push" in c for c in st["calls"])
    assert selfupdate.maybe_update(conn, evening, root=tmp_path, run=fake_git(st)) is None   # hourly at most


def test_local_edits_stop_the_update(conn, tmp_path):
    (tmp_path / ".git").mkdir()
    st = {"calls": [], "head": "a", "remote": "b", "changed": ["x"], "dirty": " M config.yaml"}
    msg = selfupdate.maybe_update(conn, datetime(2026, 11, 21, 9, 0, tzinfo=NY), root=tmp_path, run=fake_git(st))
    assert "paused" in msg and not any(c[3:4] == ["merge"] for c in st["calls"] if c[0] == "git")
