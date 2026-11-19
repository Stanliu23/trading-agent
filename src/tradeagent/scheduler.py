"""One job every 15 minutes decides what is due, by New York time. Robust to the Mac's time zone and to sleep.

- intraday: during market hours, check held positions for urgent events.
- premarket: first run at or after 08:00 on a trading day.
- close: first run at or after 16:30 on a trading day (the daily digest).
- weekly: first run at or after 09:00 on Saturday.
Each run is logged in the `runs` table (also the heartbeat); a kind already done today is not repeated.
"""

from __future__ import annotations

import dataclasses
import traceback
from datetime import datetime, time, timedelta
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

import pandas as pd

from tradeagent import account, analyst, db, emailer, macro, market, market_calendar, paperwatch, reports, schwab
from tradeagent.config import PROJECT_ROOT, Config
from tradeagent.emailer import Email, Footer, Line, Section, subject_line

NY = ZoneInfo("America/New_York")


def _hhmm(s: str) -> time:
    h, m = s.split(":")
    return time(int(h), int(m))


def due(config: Config, now: datetime, done_today: set[str]) -> list[str]:
    local = now.astimezone(NY)
    sess = market_calendar.session(local.date())
    out = []
    if sess and _hhmm(config.schedule.premarket) <= local.time() < sess.open.time() and "premarket" not in done_today:
        out.append("premarket")
    if sess and sess.open <= local < sess.close:
        out.append("intraday")
    if sess and local.time() >= _hhmm(config.schedule.close) and "close" not in done_today:
        out.append("close")
    if local.strftime("%A").lower() == config.schedule.weekly.day and local.time() >= _hhmm(config.schedule.weekly.time) \
            and "weekly" not in done_today:
        out.append("weekly")
    return out


def _done_today(conn, now: datetime) -> set[str]:
    day = now.astimezone(NY).date().isoformat()
    rows = conn.execute("SELECT kind FROM runs WHERE substr(started_at,1,10) = ? AND status IN ('ok','quiet')", (day,))
    return {r["kind"] for r in rows}


def _sent(conn) -> set[str]:
    return {r["key"] for r in conn.execute("SELECT key FROM sent_keys")}


def _mark_sent(conn, keys: list[str], now: datetime) -> None:
    conn.executemany("INSERT OR IGNORE INTO sent_keys(key, sent_at) VALUES (?, ?)",
                     [(k, now.isoformat(timespec="seconds")) for k in keys])
    conn.commit()


def _deliver(em: emailer.Email, config: Config, conn, dry_run: bool, out_dir: Path) -> str:
    days = schwab.login_days_left(conn)
    if days is not None:
        em = dataclasses.replace(em, footer=dataclasses.replace(em.footer, login_days_left=max(days, 0)))
    if dry_run:
        out_dir.mkdir(parents=True, exist_ok=True)
        stem = f"{em.kind}-{datetime.now():%Y%m%d-%H%M%S}"
        (out_dir / f"{stem}.txt").write_text(f"Subject: {em.subject}\n\n" + emailer.render_text(em, config.mode == "shadow"))
        (out_dir / f"{stem}.html").write_text("<!doctype html><meta charset='utf-8'>" + emailer.render_html(em, config.mode == "shadow"))
        return f"previewed {stem}"
    return emailer.send(em, config, conn=conn)


def _system_lines(conn, now: datetime) -> list[Line]:
    day = now.astimezone(NY).date().isoformat()
    n_ok = conn.execute("SELECT COUNT(*) FROM runs WHERE substr(started_at,1,10)=? AND status IN ('ok','quiet')", (day,)).fetchone()[0]
    n_err = conn.execute("SELECT COUNT(*) FROM runs WHERE substr(started_at,1,10)=? AND status='error'", (day,)).fetchone()[0]
    ai = analyst.runs_today(conn, day)
    return [Line(f"Runs today: {n_ok} OK, {n_err} errors · AI write-ups today: {ai}", "run log")]


def _macro_lines(state: account.AccountState, config: Config, conn, now: datetime) -> tuple[list[Line], list[str]]:
    holdings = sorted({p.symbol for p in state.sim.open_positions})
    if not holdings:
        return [], []
    items = macro.fetch_items(config, yahoo_symbols=holdings)
    rep = macro.run_once(items, holdings, config, now.astimezone(ZoneInfo("UTC")), already_reported=_sent(conn))
    y10 = macro.fred_series("DGS10")
    fed = macro.fed_change_days(macro.fred_series("DFEDTARU"))
    sens = {h: macro.rate_sensitivity(state.bars[h], y10, h, config) for h in holdings if h in state.bars}
    imp = {h: [macro.fed_move_impact(state.bars[h], v, config, k) for k, v in fed.items()] for h in holdings if h in state.bars}
    lines = macro.email_lines(rep, sens, imp, config)
    return lines, [macro.story_key(st) for st, _ in rep.confirmed]


def run_kind(kind: str, config: Config, *, now: Optional[datetime] = None, dry_run: bool = False,
             start: Optional[str] = None) -> str:
    now = now or datetime.now(NY)
    conn = db.connect(db.init_db())
    started = now.isoformat(timespec="seconds")
    cur = conn.execute("INSERT INTO runs(kind, started_at, status) VALUES (?, ?, 'running')",
                       (kind if kind in ("intraday", "premarket", "close", "weekly") else "manual", started))
    run_id = cur.lastrowid
    conn.commit()
    out_dir = PROJECT_ROOT / "data" / "run_preview"
    status, detail = "ok", ""
    try:
        state = account.build(config, start=start)
        if kind == "intraday":
            quotes = {p.symbol: q for p in state.sim.open_positions if (q := market.quote(p.symbol))}
            sigmas = {}
            for p in state.sim.open_positions:
                c = state.bars[p.symbol]["close"]
                sigmas[p.symbol] = float(c.pct_change().dropna().tail(config.triggers.sigma_lookback_days).std())
            em, keys = reports.urgent(state, quotes, config, sigmas=sigmas, fired=_sent(conn), now=pd.Timestamp(now))
            if em is None:
                status, detail = "quiet", "nothing urgent"
            else:
                detail = _deliver(em, config, conn, dry_run, out_dir)
                if not dry_run:
                    _mark_sent(conn, keys, now)
        elif kind == "premarket":
            lines, keys = _macro_lines(state, config, conn, now)
            detail = _deliver(reports.premarket(state, config, macro_lines=lines), config, conn, dry_run, out_dir)
            if not dry_run:
                _mark_sent(conn, keys, now)
        elif kind == "close":
            lines, keys = _macro_lines(state, config, conn, now)
            em = reports.digest(state, config, macro_lines=lines, conn=conn, system_lines=_system_lines(conn, now))
            detail = _deliver(em, config, conn, dry_run, out_dir)
            if not dry_run:
                _mark_sent(conn, keys, now)
        elif kind == "weekly":
            watch = [Line(f"{g.setup_id} on {g.group} stocks: {g.trades} closed paper trades since "
                          f"{config.paper_watch.watch_start}, avg {g.avg_r:+.2f}R.", "paper watch")
                     for g in paperwatch.compare(state.bars, config, config.paper_watch.watch_start) if g.avg_r is not None]
            em = reports.weekly(state, config, watch_lines=watch, system_lines=_system_lines(conn, now))
            detail = _deliver(em, config, conn, dry_run, out_dir)
        else:
            raise ValueError(kind)
    except account.NotStarted as exc:
        status, detail = "quiet", str(exc)
    except Exception as exc:
        status, detail = "error", f"{type(exc).__name__}: {exc}"
        (PROJECT_ROOT / "logs").mkdir(exist_ok=True)
        with open(PROJECT_ROOT / "logs" / "errors.log", "a") as f:
            f.write(f"{started} {kind}\n{traceback.format_exc()}\n")
    conn.execute("UPDATE runs SET finished_at=?, status=?, detail=? WHERE id=?",
                 (datetime.now(NY).isoformat(timespec="seconds"), status, detail[:500], run_id))
    conn.commit()
    conn.close()
    return f"{kind}: {status} ({detail})"


def login_reminder_email(days_left: int, login_time: datetime) -> Email:
    expired = days_left < 0
    when = f"{login_time.astimezone(NY):%b %d %H:%M} ET"
    lead = (Line(f"Your Schwab login expired. Account data is frozen at the last read; log in again to resume.", "login log")
            if expired else
            Line(f"Your Schwab login expires within {days_left + 1} day{'s' if days_left else ''}. Log in again to keep "
                 f"account data flowing.", "login log"))
    steps = [Line("On the always-on Mac, in the trading-agent folder, run: uv run tradeagent schwab-login", None),
             Line("Log in, tick your account, approve, then paste the address the browser lands on.", None),
             Line(f"Last login: {when}. Schwab logins last 7 days.", "login log")]
    return Email("reminder", subject_line("reminder", ["Schwab login " + ("expired" if expired else "expires soon")], False),
                 lead, [Section("What to do", steps)],
                 Footer(f"{datetime.now(NY):%H:%M} ET, {datetime.now(NY):%b %d}", max(days_left, 0), "Schwab"))


def _login_reminder(config: Config, conn, now: datetime, dry_run: bool) -> Optional[str]:
    """Day-6 reminder, and one more when the login has expired. Each sent once per login."""
    at = schwab.login_at(conn)
    if at is None or now - at < timedelta(days=config.schwab.login_reminder_day):
        return None
    left = schwab.login_days_left(conn, now)
    key = f"schwab-login-{'expired' if left < 0 else 'reminder'}-{at.isoformat(timespec='minutes')}"
    if key in _sent(conn):
        return None
    status = _deliver(login_reminder_email(left, at), config, conn, dry_run, PROJECT_ROOT / "data" / "run_preview")
    if not dry_run:
        _mark_sent(conn, [key], now)
    return f"schwab login reminder: {status}"


def tick(config: Config, *, now: Optional[datetime] = None, dry_run: bool = False) -> list[str]:
    """What launchd calls every 15 minutes."""
    now = now or datetime.now(NY)
    conn = db.connect(db.init_db())
    todo = due(config, now, _done_today(conn, now))
    out = []
    try:
        if (r := _login_reminder(config, conn, now, dry_run)):
            out.append(r)
    except Exception as exc:
        out.append(f"schwab login reminder: error ({type(exc).__name__}: {exc})")
    conn.close()
    return out + [run_kind(k, config, now=now, dry_run=dry_run) for k in todo]


LAUNCHD = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.tradeagent.tick</string>
  <key>ProgramArguments</key>
  <array>
    <string>{uv}</string><string>run</string><string>--directory</string><string>{root}</string>
    <string>tradeagent</string><string>tick</string>
  </array>
  <key>StartInterval</key><integer>900</integer>
  <key>RunAtLoad</key><true/>
  <key>StandardOutPath</key><string>{root}/logs/tick.log</string>
  <key>StandardErrorPath</key><string>{root}/logs/tick.err.log</string>
  <key>EnvironmentVariables</key>
  <dict><key>PATH</key><string>{path}</string></dict>
</dict>
</plist>
"""


def launchd_plist(uv_path: str, root: Path, path_env: str) -> str:
    return LAUNCHD.format(uv=uv_path, root=root, path=path_env)
