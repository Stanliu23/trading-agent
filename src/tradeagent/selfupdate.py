"""Auto-sync on the always-on Mac: pull new code from GitHub by itself, outside market hours.

Rules:
- once a day: the first run at or after 06:00 New York time (before the 08:00 premarket job), so each trading day
  starts on the newest code and nothing changes mid-session;
- fast-forward only from origin/main, and only if nothing was edited locally (otherwise it stops and says so);
  files that commands on this Mac rewrite (``GENERATED_FILES``) are not edits: GitHub's copy replaces them first;
- if the dependencies changed, ``uv sync --extra analyst``; if the setup rules changed, rebuild the setup statistics;
- the result is kept in the database and shown in the next email's System section.
This Mac never pushes anything.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from datetime import datetime, time
from pathlib import Path
from typing import Callable, Optional
from zoneinfo import ZoneInfo

from tradeagent import db
from tradeagent.config import PROJECT_ROOT

NY = ZoneInfo("America/New_York")
DAILY_AT = time(6, 0)                         # New York time
DEPENDENCY_FILES = ("pyproject.toml", "uv.lock")
SETUP_FILES = ("src/tradeagent/setups/", "config.yaml")
# rewritten by `backtest-setups`, which this module itself runs; the agent reads data/setup_stats.json instead
GENERATED_FILES = ("docs/SETUP_STATS.md",)

Run = Callable[..., subprocess.CompletedProcess]


def _git(args: list[str], root: Path, run: Run) -> str:
    out = run(["git", "-C", str(root), *args], capture_output=True, text=True, timeout=120)
    if out.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {(out.stderr or out.stdout).strip()[:200]}")
    return out.stdout.strip()


def due_today(conn, now: datetime) -> bool:
    """True for the first check at or after 06:00 New York time each day."""
    local = now.astimezone(NY)
    last = db.get_meta(conn, "update_checked_at")
    done_today = last is not None and datetime.fromisoformat(last).astimezone(NY).date() == local.date()
    return local.time() >= DAILY_AT and not done_today


def _set(conn, key: str, value: str) -> None:
    conn.execute("INSERT INTO meta(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                 (key, value))
    conn.commit()


def maybe_update(conn, now: datetime, *, root: Path = PROJECT_ROOT, run: Run = subprocess.run,
                 force: bool = False) -> Optional[str]:
    """Returns a one-line result when it did something worth reporting, else None."""
    if not force and not due_today(conn, now):
        return None
    _set(conn, "update_checked_at", now.isoformat(timespec="seconds"))
    if not (root / ".git").exists():
        return None
    try:
        _git(["fetch", "--quiet", "origin", "main"], root, run)
        head, remote = _git(["rev-parse", "HEAD"], root, run), _git(["rev-parse", "origin/main"], root, run)
        if head == remote:
            return None
        # Restore only generated files that show as changed: restoring a file the repo no longer has would fail on
        # every run and leave this Mac unable to pull the fix.
        dirty = {line.split(maxsplit=1)[-1] for line in
                 _git(["status", "--porcelain", "--untracked-files=no"], root, run).splitlines() if line.strip()}
        regenerated = [f for f in GENERATED_FILES if f in dirty]
        if regenerated:
            _git(["checkout", "--", *regenerated], root, run)
        if _git(["status", "--porcelain", "--untracked-files=no"], root, run):
            msg = "Auto-update paused: files were edited on this Mac. Nothing was changed."
            _set(conn, "last_update", f"{now:%Y-%m-%d %H:%M} {msg}")
            return msg
        changed = _git(["diff", "--name-only", head, remote], root, run).splitlines()
        _git(["merge", "--ff-only", "--quiet", "origin/main"], root, run)
        subject = _git(["log", "-1", "--format=%h %s"], root, run)
        steps = []
        uv = shutil.which("uv") or os.path.expanduser("~/.local/bin/uv")
        if any(f in DEPENDENCY_FILES for f in changed):
            r = run([uv, "sync", "--python", "3.12", "--extra", "analyst"], cwd=root, capture_output=True, text=True,
                    timeout=900)
            steps.append("packages updated" if r.returncode == 0 else "package update FAILED")
        if any(f.startswith(SETUP_FILES) for f in changed):
            r = run([uv, "run", "--directory", str(root), "tradeagent", "backtest-setups"], capture_output=True,
                    text=True, timeout=1800)
            steps.append("setup statistics rebuilt" if r.returncode == 0 else "setup statistics rebuild FAILED")
        msg = f"Updated to {subject} ({len(changed)} files" + (f"; {', '.join(steps)}" if steps else "") + ")."
        _set(conn, "last_update", f"{now:%Y-%m-%d %H:%M} {msg}")
        return msg
    except Exception as exc:                       # never let an update problem stop the agent's runs
        msg = f"Auto-update failed: {exc}"
        _set(conn, "last_update", f"{now:%Y-%m-%d %H:%M} {msg}")
        return msg
