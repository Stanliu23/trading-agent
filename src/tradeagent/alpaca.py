"""Alpaca PAPER account client: the paper test's simulated brokerage. No real money can be reached.

``guard`` lets requests through only to Alpaca's paper host (paper-api.alpaca.markets). The live host
(api.alpaca.markets) and every other host are refused before anything is sent, so even a live key pasted by
mistake could not trade. Schwab stays read-only in ``schwab.py``; nothing here talks to Schwab.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Callable, Optional

from tradeagent import secrets

PAPER = "https://paper-api.alpaca.markets"
PAPER_HOST = "paper-api.alpaca.markets"


class NotPaper(RuntimeError):
    """A request aimed anywhere but Alpaca's paper host. Stopped before reaching the network."""


class AlpacaError(RuntimeError):
    pass


def guard(method: str, url: str) -> None:
    parts = urllib.parse.urlsplit(url)
    if parts.scheme != "https" or parts.netloc != PAPER_HOST or not parts.path.startswith("/v2/") or ".." in parts.path:
        raise NotPaper(f"blocked {method} {parts.netloc}{parts.path}: only Alpaca's paper account is allowed")
    if method.upper() not in ("GET", "POST"):
        raise NotPaper(f"blocked {method}: the agent never deletes or replaces in Alpaca")


Transport = Callable[[str, str, dict, Optional[bytes]], tuple[int, bytes]]


def urllib_transport(method: str, url: str, headers: dict, body: Optional[bytes]) -> tuple[int, bytes]:
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


class Client:
    """One Alpaca paper account. The main test uses alpaca_paper_key/secret; each experiment has its own pair."""

    def __init__(self, transport: Transport = urllib_transport, key_name: str = "alpaca_paper_key",
                 secret_name: str = "alpaca_paper_secret"):
        self.transport = transport
        self.key_name, self.secret_name = key_name, secret_name

    def _call(self, method: str, path: str, params: Optional[dict] = None, body: Optional[dict] = None):
        url = PAPER + path + ("?" + urllib.parse.urlencode(params) if params else "")
        guard(method, url)
        key, secret = secrets.get_secret(self.key_name), secrets.get_secret(self.secret_name)
        if not key or not secret:
            raise AlpacaError(f"{self.key_name} / {self.secret_name} are not in the Keychain (tradeagent set-secret ...)")
        status, raw = self.transport(method, url, {"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret,
                                                   "Content-Type": "application/json", "Accept": "application/json"},
                                     json.dumps(body).encode() if body is not None else None)
        data = json.loads(raw or b"null")
        if status >= 300:
            msg = data.get("message") if isinstance(data, dict) else raw[:200]
            raise AlpacaError(f"{method} {path} failed (HTTP {status}): {msg}")
        return data

    def account(self) -> dict:
        return self._call("GET", "/v2/account")

    def positions(self) -> list[dict]:
        return self._call("GET", "/v2/positions") or []

    def orders(self, after_iso: str) -> list[dict]:
        """Every order since ``after_iso`` (yours and the agent's), oldest first."""
        out, after = [], after_iso
        while True:
            page = self._call("GET", "/v2/orders", {"status": "all", "after": after, "direction": "asc",
                                                    "limit": 500, "nested": "false"}) or []
            out += page
            if len(page) < 500:
                return out
            after = page[-1]["submitted_at"]

    def market_order(self, symbol: str, side: str, client_order_id: str, *, notional: Optional[float] = None,
                     qty: Optional[float] = None) -> dict:
        """A market DAY order by dollars (buys) or shares (sells). Fractional amounts allowed."""
        if (notional is None) == (qty is None):
            raise ValueError("give exactly one of notional or qty")
        body = {"symbol": symbol, "side": side, "type": "market", "time_in_force": "day", "client_order_id": client_order_id}
        if notional is not None:
            body["notional"] = f"{notional:.2f}"
        else:
            body["qty"] = f"{qty:.9f}".rstrip("0").rstrip(".")
        return self._call("POST", "/v2/orders", body=body)
