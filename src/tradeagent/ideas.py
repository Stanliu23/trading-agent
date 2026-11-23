"""Weekly ideas from GitHub (Stanley's request, 2026-11-23).

A scheduled cloud agent searches GitHub every Friday night for trading bots and strategies, judges whether a part of
one could improve ours, and writes at most 3 proposals to research/ideas/latest.md on the `ideas` branch, never main.
The Saturday report shows them here. NOTHING is built from a proposal until Stanley approves it; an approved idea is
then built and tested on the MacBook (same pass bar, fixed before results) and only reaches main if it passes.

This module only READS the ideas branch (``git fetch`` + ``git show``); it never checks it out, merges or pushes.
Proposal format (the routine is told to write exactly this):

    # Ideas from GitHub, week of 2026-11-27
    ## 1. <title>
    - What: ...
    - Source: <repo URL>
    - License: ...
    - Better than ours because: ...
    - Would change: ...
    - How it would be tested: ...
    - Verdict: can build | cannot build (why)
"""

from __future__ import annotations

import re
import subprocess
from datetime import date, datetime
from pathlib import Path
from typing import Callable, Optional

from tradeagent.config import PROJECT_ROOT
from tradeagent.emailer import Line

BRANCH = "ideas"
PATH = "research/ideas/latest.md"
FIELDS = ("What", "Source", "License", "Better than ours because", "Would change", "How it would be tested", "Verdict")
MAX_ITEMS, MAX_FIELD = 3, 240
Run = Callable[..., subprocess.CompletedProcess]


def latest(root: Path = PROJECT_ROOT, run: Run = subprocess.run) -> Optional[str]:
    """The newest proposal file on origin/ideas, or None (no branch yet, offline, ...)."""
    try:
        f = run(["git", "-C", str(root), "fetch", "--quiet", "origin", BRANCH], capture_output=True, text=True, timeout=60)
        if f.returncode != 0:
            return None
        s = run(["git", "-C", str(root), "show", f"origin/{BRANCH}:{PATH}"], capture_output=True, text=True, timeout=30)
        return s.stdout if s.returncode == 0 else None
    except Exception:
        return None


def _clean(s: str) -> str:
    s = re.sub(r"[`*<>]", "", s).strip()
    return s if len(s) <= MAX_FIELD else s[:MAX_FIELD - 1].rstrip() + "…"


def parse(text: str) -> tuple[Optional[date], list[dict]]:
    week = None
    m = re.search(r"^#\s*Ideas from GitHub, week of (\d{4}-\d{2}-\d{2})", text, re.M)
    if m:
        week = date.fromisoformat(m.group(1))
    items = []
    for block in re.split(r"^##\s+", text, flags=re.M)[1:]:
        head, _, body = block.partition("\n")
        item = {"title": _clean(re.sub(r"^\d+\.\s*", "", head))}
        for f in FIELDS:
            fm = re.search(rf"^-\s*{re.escape(f)}:\s*(.+)$", body, re.M | re.I)
            item[f] = _clean(fm.group(1)) if fm else ""
        items.append(item)
    return week, items[:MAX_ITEMS]


def weekly_lines(now: datetime, root: Path = PROJECT_ROOT, run: Run = subprocess.run) -> list[Line]:
    text = latest(root, run)
    if not text:
        return [Line("No ideas from GitHub yet (the weekly search writes them on Friday nights).", None, "muted")]
    week, items = parse(text)
    if week is None or (now.date() - week).days > 8:
        return [Line(f"No new ideas from GitHub this week" + (f" (last list: week of {week})." if week else "."), None, "muted")]
    src = f"GitHub search, week of {week}"
    if not items:
        return [Line("The weekly GitHub search found nothing worth changing this week.", src, "muted")]
    out = []
    for i, it in enumerate(items, 1):
        e = {k: (v[:-1] if isinstance(v, str) and v.endswith(".") else v) for k, v in it.items()}   # no ".."
        out.append(Line(f"{i}. {e['title']}. {e['What']}. Better than ours because: {e['Better than ours because']}. "
                        f"Would change: {e['Would change']}. Tested by: {e['How it would be tested']}. "
                        f"Source: {e['Source']} ({e['License'] or 'license unknown'}). Verdict: {e['Verdict']}.", src))
    out.append(Line(f"Nothing above is built. To go ahead, tell Claude Code on the MacBook: \"approve idea N from the "
                    f"week of {week}\". It is then built, put through the same pass bar, and reaches main only if it "
                    f"passes and you push it.", None, "muted"))
    return out
