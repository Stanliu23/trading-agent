"""Secrets live in the macOS Keychain (via ``keyring``), never in files or the repo."""

from __future__ import annotations

import keyring

SERVICE = "trading-agent"

# Name -> phase in which it becomes required.
KNOWN_SECRETS: dict[str, str] = {
    "gmail_app_password": "Phase 3",
    "finnhub_api_key": "Phase 4",
    "schwab_app_key": "Phase 2 (Schwab API only)",
    "schwab_app_secret": "Phase 2 (Schwab API only)",
    "schwab_refresh_token": "Phase 2 (Schwab API only)",
    "alpaca_paper_key": "the Alpaca paper test",
    "alpaca_paper_secret": "the Alpaca paper test",
}


def _check_name(name: str) -> None:
    if name not in KNOWN_SECRETS:
        raise KeyError(f"unknown secret {name!r}; expected one of {sorted(KNOWN_SECRETS)}")


def get_secret(name: str) -> str | None:
    _check_name(name)
    return keyring.get_password(SERVICE, name)


def set_secret(name: str, value: str) -> None:
    _check_name(name)
    if not value:
        raise ValueError("refusing to store an empty secret")
    keyring.set_password(SERVICE, name, value)


def has_secret(name: str) -> bool:
    return get_secret(name) is not None
