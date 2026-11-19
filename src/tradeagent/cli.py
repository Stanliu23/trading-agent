"""Command line: `tradeagent doctor | init-db | set-secret NAME`."""

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


if __name__ == "__main__":
    sys.exit(main())
