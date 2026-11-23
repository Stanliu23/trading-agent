"""Ideas from proposal to kept or removed (docs/LEARNING.md, part 3). The ledger is research/ideas_ledger.json.

An approved idea that passes its backtest runs as a TRIAL behind a switch (``trials:`` in config.yaml). Its removal
rule is written in the ledger before the trial starts. Every Saturday the idea's check compares the new rule with
the old one on the same live data; if the removal rule fires, the agent switches the idea off by itself (a database
flag, so no file on the always-on Mac is edited) and the previous, already-approved rule is back from the next run.
Switching an idea back on needs Stanley's approval and a code change here.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Optional

from tradeagent import db
from tradeagent.config import PROJECT_ROOT
from tradeagent.emailer import Line

LEDGER = PROJECT_ROOT / "research" / "ideas_ledger.json"
SRC = "ideas ledger + removal rules fixed in advance (docs/LEARNING.md)"
STATUS_TEXT = {
    "proposed": "proposed, waiting for your approval",
    "approved": "approved, backtest being built",
    "backtest_failed": "failed its backtest, not used",
    "backtest_passed": "passed its backtest, waiting for you to switch the trial on",
    "trial": "on trial",
    "kept": "kept after its trial",
    "removed": "removed",
    "rejected": "rejected",
    "experiment": "failed its backtest; running as a labelled paper experiment",
}


@dataclass
class Outcome:
    action: str          # waiting | keep_watching | remove
    text: str


# Filled in when an idea is built: idea id -> check(conn, bars, config, trial_start) -> Outcome.
CHECKS: dict[str, Callable[..., Outcome]] = {}


def ledger(path=LEDGER) -> list[dict]:
    return json.loads(path.read_text())["ideas"] if path.exists() else []


def removed(conn, idea_id: str) -> Optional[str]:
    return db.get_meta(conn, f"trial_removed:{idea_id}")


def remove(conn, idea_id: str, why: str, now: datetime) -> None:
    conn.execute("INSERT INTO meta(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                 (f"trial_removed:{idea_id}", f"{now:%Y-%m-%d}|{why}"[:400]))
    conn.commit()


def is_active(config, conn, idea_id: str) -> bool:
    """What the agent's code asks before using an idea: switched on in config AND not removed by its own rule."""
    return bool(config.trials.get(idea_id, False)) and removed(conn, idea_id) is None


def weekly_lines(conn, bars, config, now: datetime, save: bool = True, path=LEDGER,
                 checks: Optional[dict] = None) -> list[Line]:
    if checks is None:
        from tradeagent import trial_checks  # noqa: F401  (registers the built checks)
        checks = CHECKS
    out = []
    for idea in ledger(path):
        i, title, st = idea["id"], idea["title"], idea.get("status", "proposed")
        name = f"Idea {i} ({title})"
        if st != "trial":
            extra = f" Where: {idea['where']}" if st == "proposed" and idea.get("where") else ""
            out.append(Line(f"{name}: {STATUS_TEXT.get(st, st)}.{extra}", SRC, "muted" if st == "proposed" else None))
            continue
        gone = removed(conn, i)
        if gone:
            day, _, why = gone.partition("|")
            out.append(Line(f"{name}: REMOVED on {day} by its own rule ({why}). The previous rule is back.", SRC, "down"))
            continue
        if not config.trials.get(i):
            out.append(Line(f"{name}: on trial in the ledger but switched off in config.yaml.", SRC, "down"))
            continue
        chk = checks.get(i)
        if chk is None:
            out.append(Line(f"{name}: on trial but its removal check is not built. Switch it off until it is.", SRC, "down"))
            continue
        try:
            res = chk(conn, bars, config, idea.get("trial_start"))
        except Exception as exc:
            out.append(Line(f"{name}: its check failed this week ({type(exc).__name__}: {exc}).", SRC, "down"))
            continue
        if res.action == "remove":
            if save:
                remove(conn, i, res.text, now)
                out.append(Line(f"{name}: REMOVED today by its own rule ({res.text}). The previous rule is back from "
                                f"the next run.", SRC, "down"))
            else:
                out.append(Line(f"{name}: would be removed ({res.text}); a dry run changes nothing.", SRC, "down"))
        else:
            out.append(Line(f"{name}: on trial. {res.text}", SRC, None if res.action == "keep_watching" else "muted"))
    return out
