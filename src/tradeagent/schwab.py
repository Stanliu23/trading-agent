"""Schwab account reader (Phase 2, Plan A). READ ONLY.

Every request goes through ``_send``, which calls ``guard`` first. ``guard`` lets through exactly two things:
- GET requests under the account and market-data read paths (never anything with "order" in the path);
- the POST to the login-token endpoint (logging in and refreshing the login).
Anything else (an order, a cancel, a replace, any PUT/PATCH/DELETE) raises ``ReadOnlyViolation`` before a
single byte leaves the Mac. The Schwab app is also registered with an order limit of 0, as a second lock.

Login: Schwab's refresh token lasts 7 days from the login. ``login`` exchanges the one-time code from the
browser for tokens; the refresh token goes to the Keychain and the login time to the database, so the agent
can remind you on day 6. Each process trades the refresh token for a 30-minute access token when it starts.
"""

from __future__ import annotations

import base64
import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Callable, Optional

from tradeagent import db, secrets

API = "https://api.schwabapi.com"
AUTHORIZE_URL = API + "/v1/oauth/authorize"
TOKEN_URL = API + "/v1/oauth/token"
CALLBACK_URL = "https://127.0.0.1:8182"          # must match the app registered at developer.schwab.com exactly
READ_PREFIXES = (API + "/trader/v1/accounts", API + "/trader/v1/userPreference", API + "/marketdata/v1/")
LOGIN_DAYS = 7

# Transfers in and out of the account (Schwab transaction types). Journals are listed but not counted.
DEPOSIT_TYPES = {"ACH_RECEIPT", "CASH_RECEIPT", "WIRE_IN"}
WITHDRAWAL_TYPES = {"ACH_DISBURSEMENT", "CASH_DISBURSEMENT", "WIRE_OUT"}
SIGNED_TYPES = {"ELECTRONIC_FUND"}                 # direction from the sign of netAmount
ALL_TYPES = "TRADE,RECEIVE_AND_DELIVER,DIVIDEND_OR_INTEREST,ACH_RECEIPT,ACH_DISBURSEMENT,CASH_RECEIPT," \
            "CASH_DISBURSEMENT,ELECTRONIC_FUND,WIRE_OUT,WIRE_IN,JOURNAL,MEMORANDUM,MARGIN_CALL,MONEY_MARKET,SMA_ADJUSTMENT"


class ReadOnlyViolation(RuntimeError):
    """A request that could change the account was attempted. It was stopped before reaching the network."""


class SchwabError(RuntimeError):
    pass


class NotLoggedIn(SchwabError):
    pass


def guard(method: str, url: str) -> None:
    """Raise unless the request is a read, or the login-token call."""
    method = method.upper()
    path = urllib.parse.urlsplit(url)
    bare = f"{path.scheme}://{path.netloc}{path.path}"
    if method == "POST" and bare == TOKEN_URL:
        return
    if method == "GET" and bare.startswith(READ_PREFIXES) and "order" not in path.path.lower():
        return
    raise ReadOnlyViolation(f"blocked {method} {path.path}: this agent only reads the account")


Transport = Callable[[str, str, dict, Optional[bytes]], tuple[int, bytes]]


def urllib_transport(method: str, url: str, headers: dict, body: Optional[bytes]) -> tuple[int, bytes]:
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


def _send(transport: Transport, method: str, url: str, headers: dict, body: Optional[bytes] = None) -> tuple[int, bytes]:
    guard(method, url)                      # the only way out of this module
    return transport(method, url, headers, body)


# --- login --------------------------------------------------------------------------

def authorize_url(app_key: str) -> str:
    return f"{AUTHORIZE_URL}?" + urllib.parse.urlencode({"client_id": app_key, "redirect_uri": CALLBACK_URL})


def code_from_redirect(pasted: str) -> str:
    """The browser lands on https://127.0.0.1:8182/?code=...&session=... ; take the code from it."""
    q = urllib.parse.parse_qs(urllib.parse.urlsplit(pasted.strip()).query)
    if "code" not in q:
        raise SchwabError("that address has no code= in it; copy the whole address bar after approving")
    return q["code"][0]                     # parse_qs already decodes %40 -> @


def _keys() -> tuple[str, str]:
    key, secret = secrets.get_secret("schwab_app_key"), secrets.get_secret("schwab_app_secret")
    if not key or not secret:
        raise NotLoggedIn("schwab_app_key / schwab_app_secret are not in the Keychain (tradeagent set-secret ...)")
    return key, secret


def _token_call(form: dict, transport: Transport) -> dict:
    key, secret = _keys()
    basic = base64.b64encode(f"{key}:{secret}".encode()).decode()
    status, body = _send(transport, "POST", TOKEN_URL,
                         {"Authorization": f"Basic {basic}", "Content-Type": "application/x-www-form-urlencoded"},
                         urllib.parse.urlencode(form).encode())
    data = json.loads(body or b"{}")
    if status != 200 or "access_token" not in data:
        raise SchwabError(f"Schwab login refused (HTTP {status}): {data.get('error_description') or data.get('error') or body[:200]!r}")
    return data


def login(pasted_redirect: str, *, conn=None, transport: Transport = urllib_transport,
          now: Optional[datetime] = None) -> datetime:
    """Finish the browser login: exchange the code, keep the refresh token, record the login time."""
    data = _token_call({"grant_type": "authorization_code", "code": code_from_redirect(pasted_redirect),
                        "redirect_uri": CALLBACK_URL}, transport)
    secrets.set_secret("schwab_refresh_token", data["refresh_token"])
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    own = conn is None
    conn = conn or db.connect(db.init_db())
    try:
        conn.execute("INSERT INTO meta(key, value) VALUES ('schwab_login_at', ?) "
                     "ON CONFLICT(key) DO UPDATE SET value = excluded.value", (now.isoformat(timespec="seconds"),))
        conn.commit()
    finally:
        if own:
            conn.close()
    return now


def login_at(conn) -> Optional[datetime]:
    v = db.get_meta(conn, "schwab_login_at")
    return datetime.fromisoformat(v) if v else None


def login_days_left(conn, now: Optional[datetime] = None) -> Optional[int]:
    """Whole days until the 7-day login runs out (0 = expires within a day, negative = expired); None if never logged in."""
    at = login_at(conn)
    if at is None:
        return None
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    left = at + timedelta(days=LOGIN_DAYS) - now
    return left.days if left >= timedelta(0) else -1


# --- reading ------------------------------------------------------------------------

@dataclass
class Holding:
    symbol: str
    asset_type: str
    quantity: float                # fractional shares allowed
    avg_price: float
    market_value: float

    @property
    def price(self) -> float:
        return self.market_value / self.quantity if self.quantity else 0.0


@dataclass
class Snapshot:
    taken_at: datetime
    account_type: str
    account_value: float           # Schwab's liquidation value
    cash: float
    money_market: float
    holdings: list[Holding] = field(default_factory=list)

    @property
    def unexplained(self) -> float:
        """Account value minus (cash + money market + holdings). 0.00 when Schwab's numbers add up."""
        return round(self.account_value - self.cash - self.money_market - sum(h.market_value for h in self.holdings), 2)


@dataclass(frozen=True)
class Transfer:
    day: date
    amount: float                  # + in, - out
    kind: str                      # Schwab transaction type
    counted: bool                  # False for journals: shown to you, not treated as a deposit


class Client:
    """Read-only Schwab client. One access token per process, refreshed from the Keychain's refresh token."""

    def __init__(self, transport: Transport = urllib_transport):
        self.transport = transport
        self._token: Optional[str] = None
        self._hash: Optional[str] = None

    def _access_token(self) -> str:
        if self._token is None:
            refresh = secrets.get_secret("schwab_refresh_token")
            if not refresh:
                raise NotLoggedIn("no Schwab login yet: run `uv run tradeagent schwab-login`")
            try:
                data = _token_call({"grant_type": "refresh_token", "refresh_token": refresh}, self.transport)
            except SchwabError as exc:
                raise NotLoggedIn(f"Schwab login expired or refused; run `uv run tradeagent schwab-login` ({exc})") from exc
            if data.get("refresh_token") and data["refresh_token"] != refresh:
                secrets.set_secret("schwab_refresh_token", data["refresh_token"])
            self._token = data["access_token"]
        return self._token

    def get(self, path: str, params: Optional[dict] = None):
        url = API + path + ("?" + urllib.parse.urlencode(params) if params else "")
        status, body = _send(self.transport, "GET", url,
                             {"Authorization": f"Bearer {self._access_token()}", "Accept": "application/json"})
        if status != 200:
            raise SchwabError(f"GET {path} failed (HTTP {status}): {body[:200]!r}")
        return json.loads(body or b"null")

    def account_hash(self) -> str:
        """The encrypted id Schwab uses in URLs. Exactly one linked account is expected."""
        if self._hash is None:
            rows = self.get("/trader/v1/accounts/accountNumbers")
            if not rows:
                raise SchwabError("no account was linked during the Schwab login; log in again and tick your account")
            if len(rows) > 1:
                raise SchwabError(f"{len(rows)} accounts linked; this agent expects one (log in again and tick only one)")
            self._hash = rows[0]["hashValue"]
        return self._hash

    def raw_account(self) -> dict:
        return self.get(f"/trader/v1/accounts/{self.account_hash()}", {"fields": "positions"})

    def snapshot(self, now: Optional[datetime] = None) -> Snapshot:
        return parse_account(self.raw_account(), now or datetime.now(timezone.utc))

    def raw_transactions(self, start: date, end: date) -> list[dict]:
        out, a = [], start
        while a <= end:                                  # Schwab allows at most one year per request
            b = min(end, a + timedelta(days=364))
            out += self.get(f"/trader/v1/accounts/{self.account_hash()}/transactions",
                            {"startDate": f"{a.isoformat()}T00:00:00.000Z", "endDate": f"{b.isoformat()}T23:59:59.000Z",
                             "types": ALL_TYPES}) or []
            a = b + timedelta(days=1)
        return out

    def transfers(self, start: date, end: date) -> list[Transfer]:
        return parse_transfers(self.raw_transactions(start, end))


def masked(account_number: str) -> str:
    return f"…{str(account_number)[-3:]}" if account_number else "…"


def parse_account(raw: dict, now: datetime) -> Snapshot:
    acct = raw.get("securitiesAccount", raw)
    bal = acct.get("currentBalances") or {}
    holdings = []
    for p in acct.get("positions") or []:
        inst = p.get("instrument") or {}
        long_q, short_q = float(p.get("longQuantity") or 0), float(p.get("shortQuantity") or 0)
        if short_q:
            raise SchwabError(f"short position in {inst.get('symbol')}: the agent's rules allow no shorts")
        if inst.get("assetType") == "CASH_EQUIVALENT" or not long_q:
            continue                                     # sweep / money market is counted as cash below
        holdings.append(Holding(inst.get("symbol", "?"), inst.get("assetType", "?"), long_q,
                                float(p.get("averagePrice") or 0), float(p.get("marketValue") or 0)))
    mm = float(bal.get("moneyMarketFund") or 0)
    cash = float(bal["totalCash"]) if bal.get("totalCash") is not None else float(bal.get("cashBalance") or 0)
    return Snapshot(now, acct.get("type", "?"), float(bal.get("liquidationValue") or 0), cash, mm,
                    sorted(holdings, key=lambda h: h.symbol))


def parse_transfers(rows: list[dict]) -> list[Transfer]:
    out = []
    for t in rows:
        kind, amt = t.get("type", ""), float(t.get("netAmount") or 0)
        when = (t.get("time") or t.get("tradeDate") or "")[:10]
        if not when or not amt:
            continue
        if kind in DEPOSIT_TYPES | WITHDRAWAL_TYPES | SIGNED_TYPES:
            out.append(Transfer(date.fromisoformat(when), amt, kind, True))
        elif kind == "JOURNAL":
            out.append(Transfer(date.fromisoformat(when), amt, kind, False))
    return sorted(out, key=lambda x: x.day)


# --- buckets and storage ----------------------------------------------------------------

def bucket_of(conn, symbol: str) -> Optional[str]:
    """Your tag first; else the bucket of the latest buy recommendation for the symbol (then saved as a tag)."""
    row = conn.execute("SELECT bucket FROM bucket_tags WHERE symbol = ?", (symbol,)).fetchone()
    if row:
        return row["bucket"]
    rec = conn.execute("SELECT bucket FROM recommendations WHERE symbol = ? AND action IN ('buy','add') "
                       "ORDER BY created_at DESC LIMIT 1", (symbol,)).fetchone()
    if rec:
        tag(conn, symbol, rec["bucket"], "recommendation")
        return rec["bucket"]
    return None


def tag(conn, symbol: str, bucket: str, source: str = "you") -> None:
    conn.execute("INSERT INTO bucket_tags(symbol, bucket, tagged_at, source) VALUES (?,?,?,?) "
                 "ON CONFLICT(symbol) DO UPDATE SET bucket = excluded.bucket, tagged_at = excluded.tagged_at, "
                 "source = excluded.source",
                 (symbol.upper(), bucket, datetime.now(timezone.utc).isoformat(timespec="seconds"), source))
    conn.commit()


def save_snapshot(conn, snap: Snapshot) -> tuple[int, list[str]]:
    """Store the snapshot with each holding's bucket. Returns (snapshot id, untagged symbols)."""
    buckets = {h.symbol: bucket_of(conn, h.symbol) for h in snap.holdings}
    lt = sum(h.market_value for h in snap.holdings if buckets[h.symbol] == "long_term")
    st = sum(h.market_value for h in snap.holdings if buckets[h.symbol] == "short_term")
    cur = conn.execute("INSERT INTO snapshots(taken_at, source, account_value, cash, long_term_value, short_term_value) "
                       "VALUES (?,?,?,?,?,?)", (snap.taken_at.isoformat(timespec="seconds"), "schwab_api",
                                               snap.account_value, snap.cash + snap.money_market, lt, st))
    sid = cur.lastrowid
    conn.executemany("INSERT INTO positions(snapshot_id, symbol, quantity, price, market_value, bucket) VALUES (?,?,?,?,?,?)",
                     [(sid, h.symbol, h.quantity, h.price, h.market_value, buckets[h.symbol]) for h in snap.holdings])
    conn.commit()
    return sid, sorted(s for s, b in buckets.items() if b is None)
