"""Command line: `tradeagent --help` lists every command."""

from __future__ import annotations

import argparse
import getpass
import sys

from tradeagent import db, doctor, secrets


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="tradeagent", description="Personal read-only trading research agent.")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("doctor", help="check every prerequisite")
    sub.add_parser("init-db", help="create the local database")
    s = sub.add_parser("set-secret", help="store a secret in the macOS Keychain (prompted, not echoed)")
    s.add_argument("name", choices=sorted(secrets.KNOWN_SECRETS))
    sub.add_parser("backtest-setups", help="backtest the setup library and write docs/SETUP_STATS.md")
    rk = sub.add_parser("run", help="run one job now: intraday | premarket | close | weekly")
    rk.add_argument("kind", choices=["intraday", "premarket", "close", "weekly"])
    rk.add_argument("--dry-run", action="store_true", help="write the email to data/run_preview/ instead of sending")
    rk.add_argument("--start", help="shadow start date override (previews only)")
    tk = sub.add_parser("tick", help="what the 15-minute schedule calls: runs whatever is due (New York time)")
    tk.add_argument("--dry-run", action="store_true")
    sub.add_parser("launchd-plist", help="print the launchd job file for the always-on Mac")
    sub.add_parser("analyst-demo", help="replay 5 past alerts end to end into data/analyst_demo/ (uses Claude if signed in)")
    ep = sub.add_parser("email-preview", help="write the 4 sample emails as HTML + text to data/email_preview/")
    sub.add_parser("email-check", help="log in to the agent's Gmail without sending anything")
    et = sub.add_parser("email-test", help="send the 4 sample emails to your inbox")
    et.add_argument("--yes", action="store_true", help="confirm sending")
    sub.add_parser("paper-check", help="connect to the Alpaca PAPER account and show it (places nothing)")
    sub.add_parser("schwab-login", help="log in to Schwab (every 7 days): opens the login page, then paste the address it lands on")
    sn = sub.add_parser("snapshot", help="read the Schwab account now (read only) and save a snapshot")
    sn.add_argument("--days", type=int, default=90, help="also list deposits/withdrawals from the last N days")
    tg = sub.add_parser("tag", help="put a holding in a bucket: tag SYMBOL long_term|short_term")
    tg.add_argument("symbol")
    tg.add_argument("bucket", choices=["long_term", "short_term"])
    r = sub.add_parser("replay", help="replay recent months with a hypothetical account; writes docs/REPLAY.md")
    r.add_argument("--months", type=int, default=6)
    r.add_argument("--start-cash", type=float, default=300)
    r.add_argument("--monthly", type=float, default=250)
    r.add_argument("--no-news", action="store_true")
    args = parser.parse_args(argv)

    if args.command in ("email-preview", "email-check", "email-test"):
        from tradeagent import email_samples, emailer
        from tradeagent.config import PROJECT_ROOT, load_config
        cfg = load_config()
        shadow = cfg.mode == "shadow"
        if args.command == "email-preview":
            out = PROJECT_ROOT / "data" / "email_preview"
            out.mkdir(parents=True, exist_ok=True)
            for name, build in email_samples.ALL.items():
                em = build(shadow)
                (out / f"{name}.html").write_text("<!doctype html><meta charset='utf-8'><meta name='viewport' content='width=device-width'>"
                                                  + emailer.render_html(em, shadow), encoding="utf-8")
                (out / f"{name}.txt").write_text(f"Subject: {em.subject}\n\n" + emailer.render_text(em, shadow), encoding="utf-8")
            print(f"wrote 4 previews to {out}")
            return 0
        if args.command == "email-check":
            print(f"Gmail login: {emailer.check_login(cfg)}")
            return 0
        if not args.yes:
            print(f"This sends 4 sample emails to {cfg.local.email.to}. Re-run with --yes to send.")
            return 1
        for name, build in email_samples.ALL.items():
            print(f"{name}: {emailer.send(build(shadow), cfg)}")
        return 0
    if args.command in ("run", "tick", "launchd-plist"):
        import os, shutil
        from tradeagent import scheduler
        from tradeagent.config import PROJECT_ROOT, load_config
        if args.command == "launchd-plist":
            print(scheduler.launchd_plist(shutil.which("uv") or os.path.expanduser("~/.local/bin/uv"), PROJECT_ROOT,
                                          os.environ.get("PATH", "/usr/bin:/bin")))
            return 0
        cfg = load_config()
        if args.command == "run":
            print(scheduler.run_kind(args.kind, cfg, dry_run=args.dry_run, start=args.start))
        else:
            for line in scheduler.tick(cfg, dry_run=args.dry_run) or ["nothing due"]:
                print(line)
        return 0
    if args.command == "analyst-demo":
        from tradeagent import analyst_demo
        from tradeagent.config import load_config
        for r in analyst_demo.run(load_config()):
            print(f"{r['alert']}: {'AI' if r['used_ai'] else 'template'}; dropped {len(r['dropped'])}; "
                  f"unsourced numbers {len(r['unsourced_numbers'])}")
            for d in r["dropped"]:
                print("   dropped:", d)
        return 0
    if args.command == "paper-check":
        from tradeagent import alpaca
        try:
            c = alpaca.Client()
            a, pos = c.account(), c.positions()
        except alpaca.AlpacaError as exc:
            print(f"Alpaca: {exc}")
            return 1
        print(f"Alpaca PAPER account {a.get('status')} (…{str(a.get('account_number', ''))[-3:]}), "
              f"paper cash ${float(a.get('cash', 0)):,.2f}, {len(pos)} position(s).")
        print("The agent sizes from its own $300 budget plus deposits; Alpaca's paper cash only needs to cover it.")
        return 0
    if args.command in ("schwab-login", "snapshot", "tag"):
        return _schwab_command(args)
    if args.command == "replay":
        from tradeagent.config import load_config
        from tradeagent.replay import run
        print(f"wrote {run(load_config(), args.months, args.start_cash, args.monthly, with_news=not args.no_news)}")
        return 0

    if args.command == "backtest-setups":
        from tradeagent.config import load_config
        from tradeagent.setups.report import write_report
        print(f"wrote {write_report(load_config())}")
        return 0

    if args.command == "doctor":
        checks = doctor.run_checks()
        print(doctor.format_report(checks))
        return 1 if any(c.status == "fail" for c in checks) else 0
    if args.command == "init-db":
        print(f"database ready: {db.init_db()}")
        return 0
    if args.command == "set-secret":
        value = getpass.getpass(f"{args.name}: ")
        secrets.set_secret(args.name, value)
        print(f"stored {args.name} in the Keychain")
        return 0
    return 2


def _schwab_command(args) -> int:
    import webbrowser
    from datetime import date, timedelta
    from tradeagent import schwab
    conn = db.connect(db.init_db())
    try:
        if args.command == "tag":
            schwab.tag(conn, args.symbol, args.bucket)
            print(f"{args.symbol.upper()} -> {args.bucket}")
            return 0
        if args.command == "schwab-login":
            key = secrets.get_secret("schwab_app_key")
            if not key:
                print("schwab_app_key is not in the Keychain: uv run tradeagent set-secret schwab_app_key")
                return 1
            url = schwab.authorize_url(key)
            print("1. A Schwab login page is opening. If it doesn't, open this address:\n   " + url)
            print("2. Log in, tick your brokerage account, and approve.")
            print("3. The browser then shows an error page at 127.0.0.1. That is expected.")
            print("   Copy the WHOLE address from the address bar and paste it below right away (the code expires in ~30 seconds).")
            webbrowser.open(url)
            when = schwab.login(input("\naddress: "), conn=conn)
            client = schwab.Client()
            rows = client.get("/trader/v1/accounts/accountNumbers")
            print(f"\nLogged in. Valid for 7 days (until {when + timedelta(days=7):%b %d %H:%M} UTC).")
            print(f"Linked accounts: {len(rows)} " + " ".join(schwab.masked(r.get('accountNumber', '')) for r in rows))
            return 0
        client = schwab.Client()
        snap = client.snapshot()
        sid, untagged = schwab.save_snapshot(conn, snap)
        print(f"Schwab account ({snap.account_type}), read {snap.taken_at:%Y-%m-%d %H:%M} UTC. Read only.\n")
        print(f"  Account value   ${snap.account_value:>12,.2f}")
        print(f"  Cash            ${snap.cash:>12,.2f}")
        if snap.money_market:
            print(f"  Money market    ${snap.money_market:>12,.2f}")
        for h in snap.holdings:
            b = schwab.bucket_of(conn, h.symbol) or "UNTAGGED"
            print(f"  {h.symbol:<6} {h.quantity:>12,.5f} sh  ${h.market_value:>10,.2f}  (avg cost ${h.avg_price:,.2f}, {b})")
        print(f"\n  Adds up: {'yes' if snap.unexplained == 0 else f'NO, ${snap.unexplained:,.2f} not explained'}")
        if untagged:
            print("  Untagged holdings (tell the agent which bucket): " + ", ".join(untagged))
            print("    e.g. uv run tradeagent tag " + untagged[0] + " long_term")
        moves = client.transfers(date.today() - timedelta(days=args.days), date.today())
        print(f"\nMoney in/out, last {args.days} days: " + ("none" if not moves else ""))
        for t in moves:
            note = "" if t.counted else "  (journal: shown, not counted as a deposit)"
            print(f"  {t.day}  {t.kind:<18} ${t.amount:>10,.2f}{note}")
        print(f"\nSaved as snapshot #{sid}. Compare these numbers with the Schwab app.")
        return 0
    except schwab.SchwabError as exc:
        print(f"Schwab: {exc}")
        return 1
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
