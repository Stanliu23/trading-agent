import json
from dataclasses import dataclass
from datetime import date, datetime
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from tradeagent import alpaca, paperbroker as pb, secrets
from tradeagent.config import load_config

DEP = [(pd.Timestamp("2026-11-19"), 300.0, {"long_term": 120.0, "short_term": 180.0})]


def order(cid, symbol, side, qty, px, day="2026-11-20", status="filled", oid=None):
    return {"id": oid or f"id-{cid}", "client_order_id": cid, "symbol": symbol, "side": side, "status": status,
            "filled_qty": str(qty) if status in ("filled", "partially_filled") else "0",
            "filled_avg_price": str(px) if status in ("filled", "partially_filled") else None,
            "filled_at": f"{day}T14:31:00Z", "submitted_at": f"{day}T13:00:00Z", "canceled_at": f"{day}T13:30:00Z"}


ENTRY = {"ta-20261120-entry-XYZ-S2": {"setup_id": "S2", "bucket": "short_term", "stop": 90.0, "target": 120.0,
                                      "max_hold": 20, "dollars": 50.0, "status": "sent", "symbol": "XYZ", "side": "buy"},
         "ta-20261120-entry-VTI-L1": {"setup_id": "L1", "bucket": "long_term", "dollars": 75.0, "status": "sent",
                                      "symbol": "VTI", "side": "buy"}}


# --- only the paper host ------------------------------------------------------------------

@pytest.mark.parametrize("method,url", [
    ("POST", "https://api.alpaca.markets/v2/orders"),                      # live trading host
    ("GET", "https://api.alpaca.markets/v2/account"),
    ("POST", "http://paper-api.alpaca.markets/v2/orders"),                 # not https
    ("POST", "https://paper-api.alpaca.markets.evil.com/v2/orders"),
    ("POST", "https://paper-api.alpaca.markets/v2/../v2/orders"),
    ("DELETE", "https://paper-api.alpaca.markets/v2/positions"),            # close-everything call
    ("PATCH", "https://paper-api.alpaca.markets/v2/orders/1")])
def test_anything_but_paper_is_blocked_before_sending(method, url, monkeypatch):
    with pytest.raises(alpaca.NotPaper):
        alpaca.guard(method, url)


def test_client_only_talks_to_the_paper_host(monkeypatch):
    monkeypatch.setattr(secrets, "get_secret", lambda n: "X")
    calls = []
    c = alpaca.Client(lambda m, u, h, b: calls.append((m, u, b)) or (200, b'{"id":"1"}'))
    c.market_order("VTI", "buy", "ta-1", notional=75)
    m, u, b = calls[0]
    assert u == "https://paper-api.alpaca.markets/v2/orders" and json.loads(b)["notional"] == "75.00"
    assert json.loads(b)["time_in_force"] == "day" and json.loads(b)["type"] == "market"


# --- rebuilding the account from Alpaca's orders --------------------------------------------

def test_agent_fills_become_lots_and_cash_moves_by_bucket():
    b = pb.book([order("ta-20261120-entry-XYZ-S2", "XYZ", "buy", 0.5, 100), order("ta-20261120-entry-VTI-L1", "VTI", "buy", 0.25, 300)],
                ENTRY, DEP, {})
    assert {(l.symbol, l.bucket, l.stop) for l in b.lots} == {("XYZ", "short_term", 90.0), ("VTI", "long_term", None)}
    assert b.cash == {"long_term": 45.0, "short_term": 130.0}


def test_your_sell_closes_the_lot_and_is_final():
    orders = [order("ta-20261120-entry-XYZ-S2", "XYZ", "buy", 0.5, 100),
              order("web-abc", "XYZ", "sell", 0.5, 104, day="2026-11-23")]
    b = pb.book(orders, ENTRY, DEP, {})
    assert b.lots == [] and b.closed[0].reason == "you" and b.cash["short_term"] == pytest.approx(182.0)
    assert any("will not buy it back" in t for _, t in b.notes)


def test_your_cancel_is_never_resent():
    b = pb.book([order("ta-20261120-entry-XYZ-S2", "XYZ", "buy", 0, 0, status="canceled")], ENTRY, DEP, {})
    assert "ta-20261120-entry-XYZ-S2" in b.yours_cancelled
    sent = []
    shadow = SimpleNamespace(bars={}, sim=SimpleNamespace(next_orders=[
        {"setup_id": "S2", "symbol": "XYZ", "dollars": 50.0, "stop": 90.0, "target": 120.0, "bucket": "short_term"}]))
    client = SimpleNamespace(market_order=lambda *a, **k: sent.append(a))
    pb.place_open(client, b, shadow, date(2026, 11, 20), ENTRY, lambda r: None, load_config())
    assert sent == []


def test_your_buy_is_untagged_until_you_tag_it_then_gets_S2_exits():
    idx = pd.bdate_range("2026-08-01", "2026-11-20")
    close = pd.Series(np.linspace(80, 100, len(idx)), idx)
    bars = {"ABC": pd.DataFrame({"open": close, "high": close + 1, "low": close - 1, "close": close, "volume": 1e6})}
    orders = [order("web-1", "ABC", "buy", 1, 100)]
    untagged = pb.book(orders, {}, DEP, {}, bars)
    assert untagged.lots[0].bucket is None and "untagged" in untagged.notes[0][1]
    tagged = pb.book(orders, {}, DEP, {"ABC": "short_term"}, bars)
    lot = tagged.lots[0]
    assert lot.origin == "you" and lot.stop == pytest.approx(100 - 2 * 2) and lot.target == pytest.approx(100 + 4 * 2)
    assert lot.max_hold == 20


def test_positions_mismatch_is_reported():
    b = pb.book([order("ta-20261120-entry-VTI-L1", "VTI", "buy", 0.25, 300)], ENTRY, DEP, {})
    assert pb.check_positions(b, [{"symbol": "VTI", "qty": "0.25"}]) == []
    assert pb.check_positions(b, [{"symbol": "VTI", "qty": "1.25"}])


# --- placing ------------------------------------------------------------------------------------

def _shadow(next_orders, bars=None):
    return SimpleNamespace(bars=bars or {}, sim=SimpleNamespace(next_orders=next_orders))


def test_buys_are_sized_to_the_bucket_cash_and_sent_once():
    b = pb.book([], {}, DEP, {})
    sent, rec = [], {}
    client = SimpleNamespace(market_order=lambda sym, side, cid, **k: sent.append((sym, side, cid, k)))
    plan = [{"setup_id": "S4", "symbol": "AAA", "dollars": 150.0, "stop": 9.0, "target": 12.0, "bucket": "short_term"},
            {"setup_id": "S2", "symbol": "BBB", "dollars": 60.0, "stop": 9.0, "target": 12.0, "bucket": "short_term"},
            {"setup_id": "L1", "symbol": "VTI", "dollars": 75.0, "stop": None, "target": None, "bucket": "long_term"}]
    record = lambda r: rec.__setitem__(r["client_order_id"], r)
    pb.place_open(client, b, _shadow(plan), date(2026, 11, 20), {}, record, load_config())
    assert [(s, k["notional"]) for s, _, _, k in sent] == [("AAA", 150.0), ("BBB", 30.0), ("VTI", 75.0)]   # 180 short-term cash
    pb.place_open(client, b, _shadow(plan), date(2026, 11, 20), rec, record, load_config())
    assert len(sent) == 3                                               # nothing sent twice


def test_failed_send_is_logged_and_retried():
    b = pb.book([], {}, DEP, {})
    rec = {}
    def boom(*a, **k):
        raise alpaca.AlpacaError("asset not fractionable")
    plan = [{"setup_id": "S2", "symbol": "AAA", "dollars": 50.0, "stop": 9.0, "target": 12.0, "bucket": "short_term"}]
    out = pb.place_open(SimpleNamespace(market_order=boom), b, _shadow(plan), date(2026, 11, 20), {},
                        lambda r: rec.__setitem__(r["client_order_id"], r), load_config())
    assert not out[0].ok and rec["ta-20261120-entry-AAA-S2"]["status"] == "failed"
    ok = []
    pb.place_open(SimpleNamespace(market_order=lambda *a, **k: ok.append(1)), b, _shadow(plan), date(2026, 11, 20), rec,
                  lambda r: None, load_config())
    assert ok == [1]


@dataclass
class Q:
    price: float
    prev_close: float = 100.0


def test_stop_target_and_time_limit_sells():
    b = pb.book([order("ta-20261120-entry-XYZ-S2", "XYZ", "buy", 0.5, 100),
                 order("ta-20261120-entry-VTI-L1", "VTI", "buy", 0.25, 300)], ENTRY, DEP, {})
    sent = []
    client = SimpleNamespace(market_order=lambda sym, side, cid, **k: sent.append((sym, side, cid, k)))
    now = datetime(2026, 11, 23, 11, 0)
    out = pb.place_watch(client, b, {"XYZ": Q(89.5), "VTI": Q(1.0)}, date(2026, 11, 23), now, {}, lambda r: None, False)
    assert [(o.symbol, o.purpose) for o in out] == [("XYZ", "stop")]       # long-term never sold on price
    assert sent[0][3]["qty"] == 0.5
    sent.clear()
    out = pb.place_watch(client, b, {"XYZ": Q(121)}, date(2026, 11, 23), now, {}, lambda r: None, False)
    assert out[0].purpose == "target"
    b.lots[0].max_hold = 2
    out = pb.place_watch(client, b, {"XYZ": Q(100)}, date(2026, 11, 23), now, {}, lambda r: None, late=True)
    assert out[0].purpose == "time"                                     # Nov 20 + Nov 23 = 2 sessions


def test_agent_sell_closes_exactly_its_lot():
    intents = {**ENTRY, "ta-20261123-stop-XYZ-S2": {"purpose": "stop", "lot_ref": "ta-20261120-entry-XYZ-S2",
                                                     "status": "sent", "symbol": "XYZ", "side": "sell"}}
    b = pb.book([order("ta-20261120-entry-XYZ-S2", "XYZ", "buy", 0.5, 100),
                 order("ta-20261123-stop-XYZ-S2", "XYZ", "sell", 0.5, 89.9, day="2026-11-23")], intents, DEP, {})
    assert b.lots == [] and b.closed[0].reason == "stop" and b.closed[0].exit == 89.9
    assert pb.day_events(b, intents, date(2026, 11, 23)) == ["Sold 0.50000 XYZ at $89.90 (stop): -10.1%."]


def test_live_keys_cannot_turn_on_orders_at_schwab():
    """The paper test changes nothing for the real account."""
    cfg = load_config()
    assert cfg.account.allow_orders is False and cfg.paper_broker.provider == "alpaca"


def test_cash_is_alpacas_real_cash_with_long_term_kept_at_its_share():
    dep = [(pd.Timestamp("2026-11-19"), 1000.0, {"long_term": 400.0, "short_term": 600.0})]
    b = pb.book([order("ta-20261120-entry-VTI-L1", "VTI", "buy", 0.8, 312.5)], ENTRY, dep, {}, actual_cash=1250.0)
    assert b.cash == {"long_term": 150.0, "short_term": 1100.0}          # $500 added in Alpaca went to short-term
