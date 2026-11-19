"""AI analyst: turns facts the code has already measured into short plain-English lines.

The AI never decides a trade and never brings its own numbers:
- the caller builds ``Fact``s (each with an id, a sentence, and a source tag);
- Claude (your local Claude Code login, via ``claude -p`` with no tools) returns JSON lines that cite fact ids;
- ``check`` drops any line that contains a number not present in the facts it cites, or cites an unknown fact;
- if the AI is off, capped for the day, unavailable, or every line fails, ``template`` writes the lines instead.

Vibe-Trading's own claude-cli provider passes a ``--restricted`` flag that the installed Claude Code CLI
(2.1.236) rejects, so this module calls ``claude -p`` directly with the same isolation flags minus that one.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Optional

from tradeagent import db
from tradeagent.config import Config
from tradeagent.emailer import Line

_NUM = re.compile(r"[−-]?\d+(?:[.,]\d+)*")

SYSTEM = """You write short lines for a personal trading email.
Rules:
- Use ONLY the facts provided. Every line must cite the ids of the facts it uses.
- Do not introduce any number, date, price or percentage that is not written in a cited fact.
- No predictions, no adjectives without numbers, no advice beyond what the facts state.
- why_now: one sentence (max 30 words) on why this alert happened today.
- lines: at most 3 short lines (max 25 words each) adding the most useful remaining facts.
Return JSON matching the schema."""

SCHEMA = {
    "type": "object",
    "properties": {
        "why_now": {"type": "object", "properties": {"text": {"type": "string"},
                                                     "facts": {"type": "array", "items": {"type": "string"}}},
                    "required": ["text", "facts"], "additionalProperties": False},
        "lines": {"type": "array", "maxItems": 3,
                  "items": {"type": "object", "properties": {"text": {"type": "string"},
                                                             "facts": {"type": "array", "items": {"type": "string"}}},
                            "required": ["text", "facts"], "additionalProperties": False}},
    },
    "required": ["why_now", "lines"], "additionalProperties": False,
}


@dataclass(frozen=True)
class Fact:
    id: str
    text: str          # a complete sentence with any numbers already in it
    source: str        # e.g. "prices 11-18", "setup S2", "SEC 8-K"


@dataclass
class Writeup:
    why_now: Line
    lines: list[Line] = field(default_factory=list)
    used_ai: bool = False
    dropped: list[str] = field(default_factory=list)   # AI lines rejected by the number check


def _norm(n: str) -> str:
    """Canonical numeric value: '1,234.50' -> '1234.5', '3.0' -> '3', '10' stays '10'. Sign is ignored
    (direction is carried by words like 'fell'/'rose')."""
    v = abs(float(n.replace("−", "-").replace(",", "")))
    return f"{round(v, 6):f}".rstrip("0").rstrip(".") or "0"


def _numbers(text: str) -> set[str]:
    out = set()
    for n in _NUM.findall(text):
        try:
            out.add(_norm(n))
        except ValueError:
            continue
    return out


def check(text: str, cited: list[str], facts: dict[str, Fact]) -> Optional[str]:
    """None if the line is acceptable, else the reason it is rejected."""
    if not cited:
        return "cites no fact"
    unknown = [c for c in cited if c not in facts]
    if unknown:
        return f"cites unknown fact {unknown}"
    allowed = set().union(*(_numbers(facts[c].text) for c in cited))
    extra = _numbers(text) - allowed
    return f"numbers not in cited facts: {sorted(extra)}" if extra else None


def _line(text: str, cited: list[str], facts: dict[str, Fact], tone="plain") -> Line:
    sources = []
    for c in cited:
        if facts[c].source not in sources:
            sources.append(facts[c].source)
    return Line(text, " + ".join(sources), tone)


def template(facts: list[Fact]) -> Writeup:
    """No-AI write-up: the first fact is 'why now', the next three are lines, verbatim."""
    first, rest = facts[0], facts[1:4]
    return Writeup(Line(first.text, first.source), [Line(f.text, f.source) for f in rest])


Runner = Callable[[str, str, dict, Config], dict]


def claude_runner(system: str, prompt: str, schema: dict, config: Config) -> dict:
    """One ``claude -p`` call on the local login: no tools, no MCP servers, no saved session."""
    exe = shutil.which("claude") or os.path.expanduser("~/.local/bin/claude")
    env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}   # always the local login
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as f:
        f.write(system)
        sys_path = f.name
    try:
        proc = subprocess.run(
            [exe, "-p", "--strict-mcp-config", "--tools", "", "--no-session-persistence", "--output-format", "json",
             "--model", config.ai.model, "--system-prompt-file", sys_path, "--json-schema", json.dumps(schema)],
            input=prompt, capture_output=True, text=True, timeout=config.ai.timeout_s, env=env)
    finally:
        os.unlink(sys_path)
    out = json.loads(proc.stdout or "{}")
    if out.get("is_error") or not out.get("structured_output"):
        raise RuntimeError(str(out.get("result") or proc.stderr)[:200])
    return out["structured_output"]


def runs_today(conn, today: str) -> int:
    return conn.execute("SELECT COUNT(*) FROM ai_runs WHERE substr(run_at,1,10) = ? AND status IN ('ok','fallback','error')",
                        (today,)).fetchone()[0]


def write(purpose: str, facts: list[Fact], config: Config, *, conn=None, runner: Runner = claude_runner,
          now: Optional[datetime] = None) -> Writeup:
    """Write the lines for one alert. Falls back to ``template`` whenever the AI can't be used safely."""
    if not facts:
        raise ValueError("no facts to write from")
    now = now or datetime.now().astimezone()
    by_id = {f.id: f for f in facts}
    own = conn is None
    conn = conn or db.connect(db.init_db())   # init_db is idempotent: adds tables new versions need
    status = "fallback"
    try:
        if not config.ai.enabled:
            return template(facts)
        if runs_today(conn, now.date().isoformat()) >= config.ai.max_runs_per_day:
            status = "capped"
            return template(facts)
        prompt = "Facts:\n" + "\n".join(f"[{f.id}] {f.text}" for f in facts) + f"\n\nWrite the lines for: {purpose}"
        try:
            out = runner(SYSTEM, prompt, SCHEMA, config)
        except Exception:
            status = "error"
            return template(facts)
        dropped = []
        wn = out.get("why_now") or {}
        why_problem = check(wn.get("text", ""), wn.get("facts", []), by_id)
        lines = []
        for item in (out.get("lines") or [])[:3]:
            problem = check(item.get("text", ""), item.get("facts", []), by_id)
            if problem:
                dropped.append(f"{item.get('text', '')!r}: {problem}")
            else:
                lines.append(_line(item["text"], item["facts"], by_id))
        if why_problem:
            dropped.insert(0, f"why_now {wn.get('text', '')!r}: {why_problem}")
            fb = template(facts)
            status = "fallback"
            return Writeup(fb.why_now, lines or fb.lines, used_ai=bool(lines), dropped=dropped)
        status = "ok"
        return Writeup(_line(wn["text"], wn["facts"], by_id), lines, used_ai=True, dropped=dropped)
    finally:
        conn.execute("INSERT INTO ai_runs(run_at, purpose, status) VALUES (?,?,?)",
                     (now.isoformat(timespec="seconds"), purpose[:80], status))
        conn.commit()
        if own:
            conn.close()
