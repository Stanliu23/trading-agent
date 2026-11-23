from datetime import date, datetime
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from tradeagent import db, dip, experiments as ex
from tradeagent.setups.library import DIP_D2

NY = dip.NY
IDX = pd.bdate_range("2026-08-03", "2026-11-23")          # last two sessions: Nov 20 (signal), Nov 23 (today)


def bars_with_dip(sym="NVDA", fall_day="2026-11-20"):
    close = pd.Series(100.0, IDX)
    close.loc[fall_day:] = 69.0                              # first close 31% below the 60-day high
    df = pd.DataFrame({"open": close, "high": close + 1, "low": close - 1, "close": close, "volume": 1e6})
    spy = pd.DataFrame({"open": 600.0, "high": 601.0, "low": 599.0, "close": 600.0, "volume": 1e6}, index=IDX)
    return {sym: df, "SPY": spy}


class Fake:
    def __init__(self, cash=1000.0):
        self.cash, self.orders_, self.sent, self.qty = cash, [], [], {}

    def account(self):
        return {"cash": str(self.cash), "equity": str(self.cash + sum(q * 69 for q in self.qty.values())),
                "account_number": "X"}

    def positions(self):
        return [{"symbol": s, "qty": str(q)} for s, q in self.qty.items() if q > 0]

    def orders(self, after):
        return list(self.orders_)

    def market_order(self, sym, side, cid, *, notional=None, qty=None):
        self.sent.append((sym, side, cid, notional, qty))
        self.orders_.append({"client_order_id": cid, "symbol": sym, "side": side, "status": "new", "filled_qty": "0",
                             "notional": notional, "qty": qty, "submitted_at": "2026-11-23T13:00:00Z"})

    def fill(self, price, day="2026-11-23"):
        for o in self.orders_:
            if o["status"] == "new":
                q = o["qty"] if o["qty"] is not None else o["notional"] / price
                o.update(status="filled", filled_qty=str(q), filled_avg_price=str(price), filled_at=f"{day}T14:31:00Z")
                sign = 1 if o["side"] == "buy" else -1
                self.qty[o["symbol"]] = self.qty.get(o["symbol"], 0) + sign * q
                self.cash -= sign * q * price


@pytest.fixture
def conn(tmp_path):
    return db.connect(db.init_db(tmp_path / "d.db"))


@pytest.fixture(autouse=True)
def switch_on(monkeypatch):
    monkeypatch.setattr(dip, "switch_on", lambda bars, cost: (True, 0.1))


EARN = {"NVDA": [date(2027, 2, 25)]}


def run(conn, f, bars, kind, when, quote=None, earnings=EARN):
    return dip.step(conn, f, bars, when.date(), when, kind, 0.25, earnings, 0.001, "2026-11-23",
                    quote=quote or (lambda s: None))


def test_signal_is_the_first_close_30pct_below_the_60_day_high():
    b = bars_with_dip()
    sig = DIP_D2.signal(b["NVDA"])
    assert bool(sig.loc["2026-11-20"]) and not bool(sig.loc["2026-11-23"])
    assert dip.candidates(b, pd.Timestamp("2026-11-20"))[0][0] == "NVDA"


def test_buys_a_quarter_of_the_account_at_premarket_one_at_a_time(conn):
    f, b = Fake(), bars_with_dip()
    run(conn, f, b, "premarket", datetime(2026, 11, 23, 8, tzinfo=NY))
    assert len(f.sent) == 1 and f.sent[0][:3] == ("NVDA", "buy", "tx-dip-20261123-buy-NVDA") and f.sent[0][3] == 250.0
    f.fill(69.5)
    run(conn, f, b, "premarket", datetime(2026, 11, 24, 8, tzinfo=NY))
    assert len(f.sent) == 1                                                  # already holding one dip


def test_unknown_or_nearby_earnings_skip_the_dip(conn):
    f, b = Fake(), bars_with_dip()
    run(conn, f, b, "premarket", datetime(2026, 11, 23, 8, tzinfo=NY), earnings={})
    run(conn, f, b, "premarket", datetime(2026, 11, 23, 8, tzinfo=NY), earnings={"NVDA": [date(2026, 12, 3)]})
    assert f.sent == []


def test_stop_profit_and_time_exits(conn, monkeypatch):
    f, b = Fake(), bars_with_dip()
    run(conn, f, b, "premarket", datetime(2026, 11, 23, 8, tzinfo=NY))
    f.fill(69.0)
    import json
    atr = json.loads(dip._intents(conn)["tx-dip-20261123-buy-NVDA"]["detail"])["atr"]   # ATR(14) at the signal close
    stop = 69.0 - 2.5 * atr
    assert atr > 2.0                                                         # the crash day widens the ATR
    run(conn, f, b, "intraday", datetime(2026, 11, 23, 11, tzinfo=NY), quote=lambda s: SimpleNamespace(price=stop + 0.5))
    assert len(f.sent) == 1                                                  # above the stop: nothing
    run(conn, f, b, "intraday", datetime(2026, 11, 23, 11, 15, tzinfo=NY), quote=lambda s: SimpleNamespace(price=stop - 0.1))
    assert f.sent[-1][1:3] == ("sell", "tx-dip-20261123-stop-NVDA")


def test_close_3pct_up_sells_at_the_next_open(conn):
    f, b = Fake(), bars_with_dip()
    run(conn, f, b, "premarket", datetime(2026, 11, 23, 8, tzinfo=NY))
    f.fill(69.0)
    b["NVDA"].loc["2026-11-23", "close"] = 71.1                              # 69 x 1.03 = 71.07
    out = run(conn, f, b, "close", datetime(2026, 11, 23, 16, 30, tzinfo=NY))
    assert "selling at the next open" in out[0]
    run(conn, f, b, "premarket", datetime(2026, 11, 24, 8, tzinfo=NY))
    assert f.sent[-1][1:3] == ("sell", "tx-dip-20261124-profit-NVDA")


def test_time_exit_after_20_sessions(conn, monkeypatch):
    f, b = Fake(), bars_with_dip()
    run(conn, f, b, "premarket", datetime(2026, 11, 23, 8, tzinfo=NY))
    f.fill(69.0)
    monkeypatch.setattr(dip, "_sessions_held", lambda a, c: 20)
    run(conn, f, b, "intraday", datetime(2026, 12, 21, 15, 45, tzinfo=NY), quote=lambda s: SimpleNamespace(price=69.0))
    assert f.sent[-1][1] == "sell" and "-time-" in f.sent[-1][2]


def test_switched_off_dip_buys_nothing(conn, monkeypatch):
    monkeypatch.setattr(dip, "switch_on", lambda bars, cost: (False, -0.3))
    f = Fake()
    out = run(conn, f, bars_with_dip(), "premarket", datetime(2026, 11, 23, 8, tzinfo=NY))
    assert f.sent == [] and "switched off" in out[0]


# --- sharing the low-volatility account -------------------------------------------------------------------------------

def test_dip_orders_are_not_mistaken_for_yours():
    orders = [{"client_order_id": "tx-lowv-202611-buy-KO", "symbol": "KO", "side": "buy", "status": "filled",
               "filled_qty": "1", "filled_avg_price": "70"},
              {"client_order_id": "tx-dip-20261123-buy-KO", "symbol": "KO", "side": "buy", "status": "filled",
               "filled_qty": "2", "filled_avg_price": "70"},
              {"client_order_id": "tx-dip-20261124-profit-KO", "symbol": "KO", "side": "sell", "status": "filled",
               "filled_qty": "2", "filled_avg_price": "72"}]
    b = ex.book(orders, [{"symbol": "KO", "qty": "1"}], "LOWV")
    assert b.agent_qty == {"KO": 1.0} and b.yours == {} and b.blocked == {}


def test_low_volatility_leaves_the_dip_slice_in_cash(conn):
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent))
    import test_experiments as T
    a = T.FakeAlpaca()
    ex.step("LOWV", a, T._flat(T._closes()), date(2026, 11, 24), conn, datetime(2026, 11, 24, 8), share=0.75)
    buys = [x for x in a.sent if x[1] == "buy"]
    assert len(buys) == 10 and sum(x[3] for x in buys) <= 750.0 and min(x[3] for x in buys) > 74
