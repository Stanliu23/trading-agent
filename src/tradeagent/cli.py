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
    r = sub.add_parser("replay", help="replay recent months with a hypothetical account; writes docs/REPLAY.md")
    r.add_argument("--months", type=int, default=6)
    r.add_argument("--start-cash", type=float, default=300)
    r.add_argument("--monthly", type=float, default=250)
    r.add_argument("--no-news", action="store_true")
    args = parser.parse_args(argv)

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
