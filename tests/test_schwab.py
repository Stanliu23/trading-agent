import json
from datetime import date, datetime, timedelta, timezone

import pytest

from tradeagent import db, schwab, scheduler, secrets
from tradeagent.config import load_config
from tradeagent.emailer import evidence_check

NOW = datetime(2026, 11, 19, 15, 0, tzinfo=timezone.utc)


@pytest.fixture
def vault(monkeypatch):
    """A fake Keychain, so tests never touch the real one."""
    store = {"schwab_app_key": "KEY", "schwab_app_secret": "SECRET", "schwab_refresh_token": "RT0"}
    monkeypatch.setattr(secrets, "get_secret", lambda n: store.get(n))
    monkeypatch.setattr(secrets, "set_secret", lambda n, v: store.__setitem__(n, v))
    return store


@pytest.fixture
def conn(tmp_path):
    return db.connect(db.init_db(tmp_path / "s.db"))


class Recorder:
    """A fake network: records every request that got past the guard, answers from a route table."""

    def __init__(self, routes=None):
        self.calls, self.routes = [], routes or {}

    def __call__(self, method, url, headers, body):
        self.calls.append((method, url, headers, body))
        for prefix, payload in self.routes.items():
            if url.startswith(prefix):
                return 200, json.dumps(payload(url) if callable(payload) else payload).encode()
        return 404, b"{}"


TOKEN = {schwab.TOKEN_URL: {"access_token": "AT", "refresh_token": "RT", "expires_in": 1800}}
ACCT = schwab.API + "/trader/v1/accounts"


# --- the read-only proof ---------------------------------------------------------------

WRITES = [("POST", f"{ACCT}/HASH/orders"), ("PUT", f"{ACCT}/HASH/orders/123"), ("DELETE", f"{ACCT}/HASH/orders/123"),
          ("PATCH", f"{ACCT}/HASH/orders/123"), ("POST", f"{ACCT}/HASH/previewOrder"),
          ("GET", f"{ACCT}/HASH/orders"), ("GET", schwab.API + "/trader/v1/orders"),
          ("POST", f"{ACCT}/HASH"), ("PUT", f"{ACCT}/HASH"), ("DELETE", f"{ACCT}/HASH"),
          ("POST", schwab.API + "/trader/v1/accounts/HASH/ORDERS"), ("GET", "https://example.com/trader/v1/accounts"),
          ("POST", schwab.TOKEN_URL + "/../../trader/v1/accounts/HASH/orders")]


@pytest.mark.parametrize("method,url", WRITES)
def test_order_and_write_calls_never_reach_the_network(method, url):
    net = Recorder()
    with pytest.raises(schwab.ReadOnlyViolation):
        schwab._send(net, method, url, {}, b'{"orderType":"MARKET"}')
    assert net.calls == []                                    # stopped before anything was sent


def test_only_reads_and_the_login_call_pass():
    for method, url in [("GET", f"{ACCT}/accountNumbers"), ("GET", f"{ACCT}/HASH?fields=positions"),
                        ("GET", f"{ACCT}/HASH/transactions?types=TRADE"), ("GET", schwab.API + "/marketdata/v1/quotes"),
                        ("POST", schwab.TOKEN_URL)]:
        schwab.guard(method, url)


def test_client_has_no_way_to_send_anything_but_get(vault):
    net = Recorder(TOKEN)
    c = schwab.Client(net)
    with pytest.raises(schwab.ReadOnlyViolation):
        c.get("/trader/v1/accounts/HASH/orders")
    assert [m for m, *_ in net.calls] == ["POST"] and net.calls[0][1] == schwab.TOKEN_URL   # only the login refresh
    assert not [n for n in dir(c) if any(w in n.lower() for w in ("order", "post", "put", "delete", "cancel", "replace"))]


def test_allow_orders_cannot_be_turned_on():
    cfg = load_config()
    with pytest.raises(ValueError):
        type(cfg.account).model_validate({**cfg.account.model_dump(), "allow_orders": True})


# --- login ------------------------------------------------------------------------

def test_code_is_taken_from_the_pasted_address():
    assert schwab.code_from_redirect("https://127.0.0.1:8182/?code=C0.abc%40&session=xyz") == "C0.abc@"
    with pytest.raises(schwab.SchwabError):
        schwab.code_from_redirect("https://127.0.0.1:8182/?error=denied")


def test_login_keeps_refresh_token_and_time(vault, conn):
    net = Recorder(TOKEN)
    schwab.login("https://127.0.0.1:8182/?code=ABC%40&session=s", conn=conn, transport=net, now=NOW)
    method, url, headers, body = net.calls[0]
    assert method == "POST" and headers["Authorization"].startswith("Basic ")
    assert b"code=ABC%40" in body and b"redirect_uri=https%3A%2F%2F127.0.0.1%3A8182" in body
    assert vault["schwab_refresh_token"] == "RT"
    assert schwab.login_days_left(conn, NOW) == 7 and schwab.login_days_left(conn, NOW + timedelta(days=6, hours=1)) == 0 and schwab.login_days_left(conn, NOW + timedelta(days=7, seconds=1)) == -1


def test_refused_refresh_says_to_log_in_again(vault):
    vault["schwab_refresh_token"] = "OLD"
    net = lambda *a: (401, b'{"error":"invalid_grant"}')
    with pytest.raises(schwab.NotLoggedIn, match="schwab-login"):
        schwab.Client(net).get(f"/trader/v1/accounts/accountNumbers")


# --- reading -----------------------------------------------------------------------

RAW = {"securitiesAccount": {"type": "CASH", "accountNumber": "12345678",
       "positions": [{"longQuantity": 0.41235, "shortQuantity": 0, "averagePrice": 290.1, "marketValue": 121.47,
                      "instrument": {"symbol": "VTI", "assetType": "COLLECTIVE_INVESTMENT"}},
                     {"longQuantity": 1.5, "shortQuantity": 0, "averagePrice": 40.0, "marketValue": 61.20,
                      "instrument": {"symbol": "XYZ", "assetType": "EQUITY"}},
                     {"longQuantity": 10, "shortQuantity": 0, "averagePrice": 1, "marketValue": 10.0,
                      "instrument": {"symbol": "SWVXX", "assetType": "CASH_EQUIVALENT"}}],
       "currentBalances": {"liquidationValue": 300.00, "cashBalance": 107.33, "moneyMarketFund": 10.0}}}


def test_snapshot_reads_fractional_shares_and_adds_up(vault):
    net = Recorder({**TOKEN, f"{ACCT}/accountNumbers": [{"accountNumber": "12345678", "hashValue": "H"}],
                    f"{ACCT}/H": RAW})
    s = schwab.Client(net).snapshot(NOW)
    assert [h.symbol for h in s.holdings] == ["VTI", "XYZ"] and s.holdings[0].quantity == 0.41235
    assert s.cash == 107.33 and s.money_market == 10.0 and s.unexplained == 0
    assert sum(1 for c in net.calls if c[1] == schwab.TOKEN_URL) == 1          # one login refresh per process


def test_short_position_is_refused():
    raw = {"securitiesAccount": {"positions": [{"longQuantity": 0, "shortQuantity": 2, "instrument": {"symbol": "X"}}],
                                 "currentBalances": {}}}
    with pytest.raises(schwab.SchwabError, match="no shorts"):
        schwab.parse_account(raw, NOW)


def test_deposits_and_withdrawals_are_found():
    rows = [{"type": "ACH_RECEIPT", "time": "2026-11-20T14:00:00+0000", "netAmount": 250.0},
            {"type": "WIRE_IN", "time": "2026-11-02T14:00:00+0000", "netAmount": 300.0},
            {"type": "ELECTRONIC_FUND", "time": "2026-12-01T14:00:00+0000", "netAmount": -50.0},
            {"type": "JOURNAL", "time": "2026-12-02T14:00:00+0000", "netAmount": 5.0},
            {"type": "TRADE", "time": "2026-11-21T14:00:00+0000", "netAmount": -121.47}]
    t = schwab.parse_transfers(rows)
    assert [(x.day.isoformat(), x.amount, x.counted) for x in t] == [
        ("2026-11-02", 300.0, True), ("2026-11-20", 250.0, True), ("2026-12-01", -50.0, True), ("2026-12-02", 5.0, False)]


def test_long_history_is_read_one_year_at_a_time(vault):
    seen = []
    net = Recorder({**TOKEN, f"{ACCT}/accountNumbers": [{"accountNumber": "1", "hashValue": "H"}],
                    f"{ACCT}/H/transactions": lambda url: seen.append(url) or []})
    schwab.Client(net).transfers(date(2025, 1, 1), date(2026, 11, 19))
    assert len(seen) == 2 and "startDate=2025-01-01" in seen[0] and "endDate=2026-11-19" in seen[1]


def test_buckets_from_recommendation_or_you(conn):
    conn.execute("INSERT INTO recommendations(created_at, profile, symbol, action, bucket, tier, stars, setup_id, size_usd,"
                 " max_loss_usd, evidence) VALUES ('2026-11-19','moderate','XYZ','buy','short_term',2,3,'S2',60,1.2,'{}')")
    snap = schwab.parse_account(RAW, NOW)
    sid, untagged = schwab.save_snapshot(conn, snap)
    assert untagged == ["VTI"]
    row = conn.execute("SELECT short_term_value, long_term_value, cash FROM snapshots WHERE id=?", (sid,)).fetchone()
    assert tuple(row) == (61.20, 0, 117.33)
    schwab.tag(conn, "vti", "long_term")
    _, untagged = schwab.save_snapshot(conn, snap)
    assert untagged == [] and schwab.bucket_of(conn, "XYZ") == "short_term"


# --- the weekly login reminder --------------------------------------------------------------

def test_day6_reminder_then_expired_notice_each_once(conn, monkeypatch):
    cfg = load_config()
    sent = []
    monkeypatch.setattr(scheduler, "_deliver", lambda em, *a: sent.append(em) or "sent")
    conn.execute("INSERT INTO meta(key, value) VALUES ('schwab_login_at', ?)", (NOW.isoformat(),))
    assert scheduler._login_reminder(cfg, conn, NOW + timedelta(days=5, hours=23), False) is None
    assert scheduler._login_reminder(cfg, conn, NOW + timedelta(days=6, hours=1), False)
    assert scheduler._login_reminder(cfg, conn, NOW + timedelta(days=6, hours=2), False) is None   # once only
    assert scheduler._login_reminder(cfg, conn, NOW + timedelta(days=7, hours=1), False)
    assert scheduler._login_reminder(cfg, conn, NOW + timedelta(days=8), False) is None
    assert "expires within 1 day" in sent[0].lead.text and "expired" in sent[1].lead.text
    assert all(evidence_check(e) == [] for e in sent)


def test_no_reminder_before_any_login(conn):
    assert scheduler._login_reminder(load_config(), conn, NOW, False) is None
