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
        elif args[:2] == ["checkout", "--"]:              # restores the named files: no longer dirty
            state["dirty"] = "\n".join(l for l in state.get("dirty", "").splitlines() if l[3:] not in args[2:])
        elif args[:1] == ["status"]:
            out = state.get("dirty", "")
        elif args[:2] == ["diff", "--name-only"]:
            out = "\n".join(state["changed"])
        elif args[:1] == ["log"]:
            out = "abc123 New rules"
        return subprocess.CompletedProcess(cmd, 0, out, "")
    return run


def test_once_a_day_from_six_am(conn, tmp_path):
    (tmp_path / ".git").mkdir()
    st = {"calls": [], "head": "a", "remote": "a", "changed": []}
    run = fake_git(st)
    assert selfupdate.maybe_update(conn, datetime(2026, 11, 23, 5, 45, tzinfo=NY), root=tmp_path, run=run) is None
    assert st["calls"] == []                                             # before 06:00: nothing
    selfupdate.maybe_update(conn, datetime(2026, 11, 23, 6, 5, tzinfo=NY), root=tmp_path, run=run)
    n = len(st["calls"])
    assert n > 0                                                         # first run after 06:00 checks
    for h in (6, 9, 12, 17, 23):
        selfupdate.maybe_update(conn, datetime(2026, 11, 23, h, 50, tzinfo=NY), root=tmp_path, run=run)
    assert len(st["calls"]) == n                                         # not again that day
    selfupdate.maybe_update(conn, datetime(2026, 11, 24, 6, 1, tzinfo=NY), root=tmp_path, run=run)
    assert len(st["calls"]) > n                                          # next day: checks again


def test_pulls_and_rebuilds_when_setups_change(conn, tmp_path):
    (tmp_path / ".git").mkdir()
    st = {"calls": [], "head": "a", "remote": "b", "changed": ["src/tradeagent/setups/library.py", "uv.lock"]}
    morning = datetime(2026, 11, 23, 6, 15, tzinfo=NY)
    msg = selfupdate.maybe_update(conn, morning, root=tmp_path, run=fake_git(st))
    assert "abc123" in msg and "packages updated" in msg and "setup statistics rebuilt" in msg
    assert any(c[3:5] == ["merge", "--ff-only"] for c in st["calls"] if c[0] == "git")
    assert not any("push" in c for c in st["calls"])
    assert selfupdate.maybe_update(conn, morning.replace(hour=20), root=tmp_path, run=fake_git(st)) is None  # once a day


def test_local_edits_stop_the_update(conn, tmp_path):
    (tmp_path / ".git").mkdir()
    st = {"calls": [], "head": "a", "remote": "b", "changed": ["x"], "dirty": " M config.yaml"}
    msg = selfupdate.maybe_update(conn, datetime(2026, 11, 21, 9, 0, tzinfo=NY), root=tmp_path, run=fake_git(st))
    assert "paused" in msg and not any(c[3:4] == ["merge"] for c in st["calls"] if c[0] == "git")


def test_rebuilt_stats_doc_does_not_block_the_next_update(conn, tmp_path):
    # backtest-setups (run by the previous update, or by hand) rewrote the tracked stats doc
    (tmp_path / ".git").mkdir()
    st = {"calls": [], "head": "a", "remote": "b", "changed": ["x"], "dirty": " M docs/SETUP_STATS.md"}
    msg = selfupdate.maybe_update(conn, datetime(2026, 11, 21, 9, 0, tzinfo=NY), root=tmp_path, run=fake_git(st))
    assert msg.startswith("Updated to abc123")
    git = [c[3:] for c in st["calls"] if c[0] == "git"]
    assert ["checkout", "--", "docs/SETUP_STATS.md"] in git
    assert git.index(["checkout", "--", "docs/SETUP_STATS.md"]) < next(i for i, a in enumerate(git) if a[:1] == ["merge"])


def test_real_edits_still_stop_the_update_alongside_the_stats_doc(conn, tmp_path):
    (tmp_path / ".git").mkdir()
    st = {"calls": [], "head": "a", "remote": "b", "changed": ["x"], "dirty": " M docs/SETUP_STATS.md\n M config.yaml"}
    msg = selfupdate.maybe_update(conn, datetime(2026, 11, 21, 9, 0, tzinfo=NY), root=tmp_path, run=fake_git(st))
    assert "paused" in msg and not any(c[3:4] == ["merge"] for c in st["calls"] if c[0] == "git")


def test_no_restore_when_already_up_to_date(conn, tmp_path):
    (tmp_path / ".git").mkdir()
    st = {"calls": [], "head": "a", "remote": "a", "changed": [], "dirty": " M docs/SETUP_STATS.md"}
    assert selfupdate.maybe_update(conn, datetime(2026, 11, 21, 9, 0, tzinfo=NY), root=tmp_path, run=fake_git(st)) is None
    assert not any(c[3:4] == ["checkout"] for c in st["calls"] if c[0] == "git")


def test_generated_file_is_only_restored_when_it_changed(conn, tmp_path):
    # a clean tree never runs the restore, so a stats doc removed from the repo later cannot break updates
    (tmp_path / ".git").mkdir()
    st = {"calls": [], "head": "a", "remote": "b", "changed": ["x"], "dirty": ""}
    msg = selfupdate.maybe_update(conn, datetime(2026, 11, 21, 9, 0, tzinfo=NY), root=tmp_path, run=fake_git(st))
    assert msg.startswith("Updated to abc123")
    assert not any(c[3:4] == ["checkout"] for c in st["calls"] if c[0] == "git")


def test_other_dirty_files_are_never_restored(conn, tmp_path):
    (tmp_path / ".git").mkdir()
    st = {"calls": [], "head": "a", "remote": "b", "changed": ["x"], "dirty": " M docs/SPEC.md"}
    msg = selfupdate.maybe_update(conn, datetime(2026, 11, 21, 9, 0, tzinfo=NY), root=tmp_path, run=fake_git(st))
    assert "paused" in msg and not any(c[3:4] == ["checkout"] for c in st["calls"] if c[0] == "git")
