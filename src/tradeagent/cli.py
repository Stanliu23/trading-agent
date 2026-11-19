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
    args = parser.parse_args(argv)

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
