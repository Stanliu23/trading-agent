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

from tradeagent import (account, alpaca, analyst, db, emailer, macro, market, market_calendar, paperbroker, paperwatch,
                        reports, schwab, secrets)
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
    sched = "substr(started_at,1,10)=? AND kind != 'manual'"                  # scheduled runs only, not dry runs
    n_ok = conn.execute(f"SELECT COUNT(*) FROM runs WHERE {sched} AND status IN ('ok','quiet')", (day,)).fetchone()[0]
    n_err = conn.execute(f"SELECT COUNT(*) FROM runs WHERE {sched} AND status='error'", (day,)).fetchone()[0]
    ai = analyst.runs_today(conn, day)
    out = [Line(f"Runs today: {n_ok} OK, {n_err} errors · AI write-ups today: {ai}", "run log")]
    upd = db.get_meta(conn, "last_update")
    if upd and upd[:10] == day:
        out.append(Line("Code: " + upd[11:], "auto-update log"))
    return out


def _macro_lines(state: account.AccountState, config: Config, conn, now: datetime) -> tuple[list[Line], list[str]]:
    from tradeagent import macro_trust
    from tradeagent.setups.library import ETFS, TRADED_STOCKS
    holdings = sorted({p.symbol for p in state.sim.open_positions})
    items = macro.fetch_items(config, yahoo_symbols=holdings)
    # news ledger: every confirmed story and the holdings/watchlist names it touches, scored 5 sessions later
    try:
        for st, who in macro.run_once(items, sorted(set(holdings) | set(TRADED_STOCKS) | set(ETFS)), config,
                                      now.astimezone(ZoneInfo("UTC"))).confirmed:
            macro_trust.log_story(conn, macro.story_key(st), now.astimezone(NY).date(), st.factor, who, sorted(st.publishers))
        macro_trust.fill_outcomes(conn, state.bars)
    except Exception:
        pass                                   # the ledger never blocks an email
    if not holdings:
        return [], []
    rep = macro.run_once(items, holdings, config, now.astimezone(ZoneInfo("UTC")), already_reported=_sent(conn))
    y10 = macro.fred_series("DGS10")
    fed = macro.fed_change_days(macro.fred_series("DFEDTARU"))
    sens = {h: macro.rate_sensitivity(state.bars[h], y10, h, config) for h in holdings if h in state.bars}
    imp = {h: [macro.fed_move_impact(state.bars[h], v, config, k) for k, v in fed.items()] for h in holdings if h in state.bars}
    lines = macro.email_lines(rep, sens, imp, config)
    return lines, [macro.story_key(st) for st, _ in rep.confirmed]


# --- Alpaca paper test ------------------------------------------------------------------------

def paper_ready(config: Config) -> bool:
    return config.paper_broker.enabled and secrets.has_secret("alpaca_paper_key") and secrets.has_secret("alpaca_paper_secret")


def _intents(conn) -> dict[str, dict]:
    return {r["client_order_id"]: dict(r) for r in conn.execute("SELECT * FROM paper_intents")}


def _recorder(conn, now: datetime):
    cols = ("client_order_id", "session", "symbol", "side", "purpose", "setup_id", "bucket", "stop", "target", "max_hold",
            "lot_ref", "dollars", "qty", "status", "detail")
    def record(row: dict) -> None:
        conn.execute(f"INSERT INTO paper_intents(placed_at, {', '.join(cols)}) VALUES (?{', ?' * len(cols)}) "
                     "ON CONFLICT(client_order_id) DO UPDATE SET status=excluded.status, detail=excluded.detail, "
                     "placed_at=excluded.placed_at",
                     (now.isoformat(timespec="seconds"), *[row.get(c) for c in cols]))
        conn.commit()
    return record


def _paper_book(conn, client, shadow: account.AccountState, today) -> paperbroker.Book:
    start = shadow.sim.daily.index[0]
    tags = {r["symbol"]: r["bucket"] for r in conn.execute("SELECT symbol, bucket FROM bucket_tags")}
    b = paperbroker.book(client.orders(f"{start:%Y-%m-%d}T00:00:00Z"), _intents(conn), shadow.sim.deposits, tags, shadow.bars,
                         actual_cash=float(client.account()["cash"]))
    b.notes += [(today, n) for n in paperbroker.check_positions(b, client.positions())]
    return b


def _paper_state(conn, client, shadow: account.AccountState, today, save_close: bool = False) -> account.AccountState:
    b = _paper_book(conn, client, shadow, today)
    hist = [dict(r) for r in conn.execute("SELECT * FROM paper_daily ORDER BY day")]
    day = shadow.day.date()
    state = paperbroker.to_state(shadow, b, hist, day, tuple(paperbroker.day_events(b, _intents(conn), today)))
    if save_close:
        r = state.sim.daily.iloc[-1]
        conn.execute("INSERT INTO paper_daily(day, value, cash_lt, cash_st, lt_value, st_value) VALUES (?,?,?,?,?,?) "
                     "ON CONFLICT(day) DO UPDATE SET value=excluded.value, cash_lt=excluded.cash_lt, cash_st=excluded.cash_st, "
                     "lt_value=excluded.lt_value, st_value=excluded.st_value",
                     (day.isoformat(), float(r["value"]), float(r["cash_lt"]), float(r["cash_st"]), float(r["lt_value"]),
                      float(r["st_value"])))
        conn.commit()
    return state


def _main_since(conn, start: str) -> Optional[float]:
    """The main paper account's change from the close before ``start`` to its latest close (no deposits in the test)."""
    rows = conn.execute("SELECT day, value FROM paper_daily ORDER BY day").fetchall()
    before = [r for r in rows if r[0] < start]
    if not rows:
        return None
    base = before[-1][1] if before else rows[0][1]
    return rows[-1][1] / base - 1 if base else None


def paper_start_balance(conn, client) -> float:
    """Alpaca's balance when the test started: read once, then kept, so the plan is sized from real money."""
    v = db.get_meta(conn, "paper_start_balance")
    if v is None:
        v = str(round(float(client.account()["equity"]), 2))
        conn.execute("INSERT INTO meta(key, value) VALUES ('paper_start_balance', ?)", (v,))
        conn.commit()
    return float(v)


def _macro_trust_lines(config: Config, conn, now: datetime, dry_run: bool) -> list[Line]:
    """Saturday: re-score the macro conditions (fixed rules), report changes and the news record so far."""
    from tradeagent import macro_rescore, macro_trust
    try:
        changes = macro_rescore.rescore(config, conn, now) if not dry_run else []
    except Exception as exc:
        changes = [f"Macro re-score failed this week ({type(exc).__name__}); last week's statuses stay."]
    act = macro_trust.active(conn)
    out = [Line(c, "macro trust score") for c in changes]
    out.append(Line("Macro conditions trusted to change trades: " + (", ".join(f"{k} → {s} ({a})" for (s, k), a in act.items())
                    if act else "none."), "macro trust score"))
    for f, v in macro_trust.news_trust(conn).items():
        out.append(Line(f"News ({f}): {v['stories']} scored stories, median {v['median']:+.1%} vs SPY over 5 sessions, "
                        f"{v['negative']:.0%} negative: {'trusted' if v['trusted'] else 'not trusted yet'}.", "news ledger"))
    return out


def _compare_lines(paper: account.AccountState, shadow: account.AccountState) -> list[Line]:
    pv, sv = paper.value(), shadow.value()
    yours = [c for c in paper.sim.trades if c.reason == "you"]
    out = [Line(f"Alpaca paper ${pv:,.2f} vs rules-only pretend account ${sv:,.2f}: {pv - sv:+,.2f}. The gap is your "
                f"changes plus real fills vs assumed prices.", f"Alpaca paper + shadow account {shadow.day:%m-%d}")]
    if yours:
        out.append(Line(f"Your own sells so far: {len(yours)}, together {sum(c.pnl for c in yours):+,.2f} vs their entry.",
                        f"Alpaca paper {paper.day:%m-%d}"))
    return out


def run_kind(kind: str, config: Config, *, now: Optional[datetime] = None, dry_run: bool = False,
             start: Optional[str] = None) -> str:
    now = now or datetime.now(NY)
    conn = db.connect(db.init_db())
    started = now.isoformat(timespec="seconds")
    # a dry run is logged as "manual": logged under its own kind it would count as today's real run, and the
    # scheduled one (orders, email) would then be skipped
    real = kind in ("intraday", "premarket", "close", "weekly") and not dry_run
    cur = conn.execute("INSERT INTO runs(kind, started_at, status) VALUES (?, ?, 'running')",
                       (kind if real else "manual", started))
    run_id = cur.lastrowid
    conn.commit()
    out_dir = PROJECT_ROOT / "data" / "run_preview"
    status, detail = "ok", ""
    try:
        today = now.astimezone(NY).date()
        sess = market_calendar.session(today)
        # during the session Yahoo already has today's unfinished bar: decide from yesterday's close
        as_of = today - pd.Timedelta(days=1).to_pytimedelta() if kind == "intraday" else None
        executed, client, start_cash = None, None, None
        if paper_ready(config):
            try:
                client = alpaca.Client()
                start_cash = paper_start_balance(conn, client)
            except alpaca.AlpacaError:
                client = None
        state = account.build(config, as_of=as_of, start=start, start_cash=start_cash)
        shadow = state
        if client is not None:
            try:
                record = _recorder(conn, now)
                if kind in ("premarket", "intraday") and sess and not dry_run:     # a dry run never places orders
                    b = _paper_book(conn, client, state, today)
                    placed = paperbroker.place_open(client, b, state, today, _intents(conn), record, config)
                    if kind == "intraday":
                        b = _paper_book(conn, client, state, today)
                        held = {l.symbol for l in b.lots}
                        quotes_p = {s_: q for s_ in held if (q := market.quote(s_))}
                        late = now.astimezone(NY) >= sess.close - pd.Timedelta(minutes=20).to_pytimedelta()
                        placed += paperbroker.place_watch(client, b, quotes_p, today, now, _intents(conn), record, late)
                        executed = [p for p in placed if p.side == "sell" and p.purpose in ("stop", "target", "time")]
                state = _paper_state(conn, client, shadow, today, save_close=(kind == "close" and not dry_run))
                if kind == "close" and not dry_run:              # fill tracker: measures only, never trades
                    from tradeagent import learning
                    start = shadow.sim.daily.index[0]
                    learning.record_fills(conn, "main", client.orders(f"{start:%Y-%m-%d}T00:00:00Z"), state.bars,
                                          paperbroker.PREFIX, _intents(conn))
            except alpaca.AlpacaError as exc:
                detail = f"Alpaca unavailable, emails use the pretend account ({exc}); "
        elif config.paper_broker.enabled:
            detail = ("Alpaca unavailable: emails use the pretend account; " if paper_ready(config)
                      else "Alpaca keys not saved: emails use the pretend account; ")
        if config.experiments and sess and kind in ("premarket", "intraday", "close"):
            from tradeagent import experiments          # own paper accounts; never raises
            detail += experiments.run_all(config, conn, state.bars, today, now, kind, dry_run, main_client=client)
        if kind == "intraday":
            quotes = {p.symbol: q for p in state.sim.open_positions if (q := market.quote(p.symbol))}
            sigmas = {}
            for p in state.sim.open_positions:
                c = state.bars[p.symbol]["close"]
                sigmas[p.symbol] = float(c.pct_change().dropna().tail(config.triggers.sigma_lookback_days).std())
            em, keys = reports.urgent(state, quotes, config, sigmas=sigmas, fired=_sent(conn), now=pd.Timestamp(now),
                                      executed=executed)
            if em is None:
                status, detail = "quiet", detail + "nothing urgent"
            else:
                detail += _deliver(em, config, conn, dry_run, out_dir)
                if not dry_run:
                    _mark_sent(conn, keys, now)
        elif kind == "premarket":
            lines, keys = _macro_lines(state, config, conn, now)
            detail += _deliver(reports.premarket(state, config, macro_lines=lines), config, conn, dry_run, out_dir)
            if not dry_run:
                _mark_sent(conn, keys, now)
        elif kind == "close":
            lines, keys = _macro_lines(state, config, conn, now)
            em = reports.digest(state, config, macro_lines=lines, conn=conn, system_lines=_system_lines(conn, now))
            detail += _deliver(em, config, conn, dry_run, out_dir)
            if not dry_run:
                _mark_sent(conn, keys, now)
        elif kind == "weekly":
            watch = [Line(f"{g.setup_id} on {g.group} stocks: {g.trades} closed paper trades since "
                          f"{config.paper_watch.watch_start}, avg {g.avg_r:+.2f}R.", "paper watch")
                     for g in paperwatch.compare(state.bars, config, config.paper_watch.watch_start) if g.avg_r is not None]
            if state is not shadow:
                watch = _compare_lines(state, shadow) + watch
            watch += _macro_trust_lines(config, conn, now, dry_run)
            if config.experiments:
                from tradeagent import experiments
                watch += experiments.weekly_lines(config, conn, state.bars, now, main_since=lambda d: _main_since(conn, d))
            from tradeagent import learning
            main_book = None
            if client is not None:
                try:
                    main_book = _paper_book(conn, client, shadow, today)
                except alpaca.AlpacaError:
                    pass
            learn = learning.weekly_lines(conn, state.bars, config, now, main_book, _intents(conn),
                                           save=not dry_run)
            from tradeagent import ideas                  # reads the `ideas` branch only; never merges or pushes
            em = reports.weekly(state, config, watch_lines=watch, system_lines=_system_lines(conn, now),
                                learning_lines=learn, ideas_lines=ideas.weekly_lines(now))
            detail += _deliver(em, config, conn, dry_run, out_dir)
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
                 (datetime.now(NY).isoformat(timespec="seconds"), status,
                  ((f"dry run of {kind}: " if dry_run else "") + detail)[:500], run_id))
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
    out = []
    if config.auto_update and not dry_run:
        from tradeagent import selfupdate
        if (u := selfupdate.maybe_update(conn, now)):
            out.append(u)
    todo = due(config, now, _done_today(conn, now))
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
