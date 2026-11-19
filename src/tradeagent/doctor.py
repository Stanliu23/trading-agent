"""`tradeagent doctor`: check every prerequisite and say what is still missing."""

from __future__ import annotations

import importlib.util
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Callable, Literal

from tradeagent import db, market_calendar, secrets
from tradeagent.config import PROJECT_ROOT, Config, active_profile_name, load_config

Status = Literal["ok", "warn", "fail"]


@dataclass(frozen=True)
class Check:
    name: str
    status: Status
    detail: str


def _python() -> Check:
    v = sys.version_info
    ok = v >= (3, 11)
    return Check("Python", "ok" if ok else "fail", f"{v.major}.{v.minor}.{v.micro}" + ("" if ok else " (need 3.11+)"))


def _local_email(config: Config) -> Check:
    email = config.local.email
    if not email.to:
        return Check("Email addresses", "fail", "config.local.yaml has no email.to")
    if not email.from_:
        return Check("Email addresses", "warn", "recipient set; agent Gmail not set yet (Phase 0)")
    return Check("Email addresses", "ok", "recipient and sender set")


def _secrets(config: Config) -> list[Check]:
    used_sources = {config.market_data.primary, config.market_data.crosscheck}
    out = []
    for name, phase in secrets.KNOWN_SECRETS.items():
        if name == "finnhub_api_key" and "finnhub" not in used_sources:
            continue  # Finnhub not in use
        try:
            present = secrets.has_secret(name)
        except Exception as exc:  # Keychain locked or unavailable
            out.append(Check(f"Keychain: {name}", "fail", f"Keychain not readable: {exc}"))
            continue
        out.append(Check(f"Keychain: {name}", "ok" if present else "warn",
                         "stored" if present else f"missing (needed in {phase})"))
    return out


def _database(path: Path) -> Check:
    try:
        db.init_db(path)
        with db.connect(path) as conn:
            version = db.get_meta(conn, "schema_version")
        return Check("Database", "ok", f"{path} (schema v{version})")
    except Exception as exc:
        return Check("Database", "fail", f"{path}: {exc}")


def _calendar(today: date) -> Check:
    try:
        nxt = market_calendar.next_session(today)
        note = " (half day)" if nxt.is_half_day else ""
        return Check("Market calendar", "ok", f"next NYSE session {nxt.day:%a %b %d}, closes {nxt.close:%H:%M} ET{note}")
    except Exception as exc:
        return Check("Market calendar", "fail", str(exc))


def _profile(config: Config, path: Path) -> Check:
    with db.connect(path) as conn:
        reached = db.ever_reached_switch(conn)
    name = active_profile_name(config, ever_reached_switch=reached)
    p = getattr(config.profiles, name)
    return Check("Risk profile", "ok",
                 f"{name}: {p.max_loss_per_trade:.0%} max loss per trade, pause at {p.drawdown_pause:.0%} drop, "
                 f"long-term {p.buckets.long_term.min:.0%}-{p.buckets.long_term.max:.0%}")


def _tool(name: str, why: str) -> Check:
    path = shutil.which(name)
    return Check(name, "ok" if path else "warn", path or f"not found ({why})")


def _vibe_trading() -> Check:
    found = importlib.util.find_spec("backtest") is not None and importlib.util.find_spec("src") is not None
    return Check("Vibe-Trading", "ok" if found else "warn",
                 "installed" if found else "not installed yet (`uv sync --extra analyst`, needed from Phase 5)")


def _claude_login(run: Callable[..., subprocess.CompletedProcess] = subprocess.run) -> Check:
    exe = shutil.which("claude")
    if not exe:
        return Check("Claude login", "warn", "claude not found (needed for AI write-ups; template is used without it)")
    try:
        out = run([exe, "auth", "status"], capture_output=True, text=True, timeout=20).stdout
        import json as _json
        ok = _json.loads(out or "{}").get("loggedIn", False)
    except Exception as exc:
        return Check("Claude login", "warn", f"could not check: {exc}")
    return Check("Claude login", "ok" if ok else "warn", "signed in" if ok else "signed out: run `claude auth login`")


def _setup_stats(root: Path) -> Check:
    p = root / "data" / "setup_stats.json"
    return Check("Setup statistics", "ok" if p.exists() else "fail",
                 "present" if p.exists() else "missing: run `uv run tradeagent backtest-setups`")


def _schedule(run: Callable[..., subprocess.CompletedProcess] = subprocess.run) -> Check:
    if sys.platform != "darwin":
        return Check("15-minute schedule", "warn", "not macOS")
    import os as _os
    try:
        rc = run(["launchctl", "print", f"gui/{_os.getuid()}/com.tradeagent.tick"], capture_output=True, text=True,
                 timeout=10).returncode
    except Exception as exc:
        return Check("15-minute schedule", "warn", f"could not check: {exc}")
    return Check("15-minute schedule", "ok" if rc == 0 else "warn",
                 "installed" if rc == 0 else "not installed (only needed on the always-on Mac; see docs/DEPLOY.md)")


def _power(run: Callable[..., subprocess.CompletedProcess] = subprocess.run) -> Check:
    if sys.platform != "darwin":
        return Check("Always-on power settings", "warn", "not macOS")
    try:
        out = run(["pmset", "-g"], capture_output=True, text=True, timeout=10).stdout
    except Exception as exc:
        return Check("Always-on power settings", "warn", f"pmset failed: {exc}")
    settings = {}
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 2:
            settings[parts[0]] = parts[1]
    problems = []
    if settings.get("sleep") not in ("0",):
        problems.append(f"system sleep is {settings.get('sleep', '?')} min (want 0)")
    if "autorestart" in settings and settings["autorestart"] != "1":
        problems.append("restart after power failure is off")
    if problems:
        return Check("Always-on power settings", "warn", "; ".join(problems) + " (only matters on the always-on Mac)")
    return Check("Always-on power settings", "ok", "never sleeps, restarts after power failure")


def run_checks(root: Path = PROJECT_ROOT, db_path: Path | None = None, today: date | None = None) -> list[Check]:
    db_path = db_path or db.DEFAULT_DB
    today = today or datetime.now(market_calendar.NY).date()
    checks = [_python()]
    try:
        config = load_config(root)
    except Exception as exc:
        return checks + [Check("Config", "fail", f"config.yaml invalid: {exc}")]
    checks.append(Check("Config", "ok", f"valid; mode={config.mode.upper()}, account reader={config.account.reader}"))
    md = config.market_data
    checks.append(Check("Market data", "ok" if md.crosscheck else "warn",
                        f"{md.primary}, cross-checked by {md.crosscheck}" if md.crosscheck
                        else f"{md.primary} only, no cross-check: a bad quote can fire a false alert"))
    if config.account.reader == "undecided":
        checks.append(Check("Account reader", "warn", "undecided: waiting on Schwab API answer (Phase 2)"))
    checks.append(_local_email(config))
    checks += _secrets(config)
    db_check = _database(db_path)
    checks.append(db_check)
    if db_check.status == "ok":
        checks.append(_profile(config, db_path))
    checks.append(_calendar(today))
    checks.append(_vibe_trading())
    checks.append(_tool("claude", "Claude Code CLI, needed from Phase 6 on the always-on Mac"))
    checks.append(_tool("git", "needed to pull updates"))
    checks.append(_setup_stats(root))
    checks.append(_claude_login())
    checks.append(_schedule())
    checks.append(_power())
    return checks


SYMBOL = {"ok": "OK  ", "warn": "WARN", "fail": "FAIL"}


def format_report(checks: list[Check]) -> str:
    width = max(len(c.name) for c in checks)
    lines = [f"[{SYMBOL[c.status]}] {c.name.ljust(width)}  {c.detail}" for c in checks]
    fails = sum(c.status == "fail" for c in checks)
    warns = sum(c.status == "warn" for c in checks)
    lines.append("")
    lines.append(f"{fails} failing, {warns} still to do, {len(checks) - fails - warns} ok")
    return "\n".join(lines)
