import importlib.util
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from tradeagent import alpaca, db, experiments as ex, secrets, strategies
from tradeagent.config import load_config

ROOT = Path(__file__).resolve().parents[1]
SYMS = [f"S{i:02d}" for i in range(15)]
IDX = pd.bdate_range("2025-06-02", "2026-12-04")


def _closes():
    rng = np.random.default_rng(7)
    data = {}
    for i, s in enumerate(SYMS):
        drift = 0.0002 * i                                   # S14 strongest trend
        vol = 0.004 + 0.002 * (i % 5)                         # five volatility levels
        data[s] = 50 * np.exp(np.cumsum(drift + vol * rng.standard_normal(len(IDX))))
    return pd.DataFrame(data, index=IDX)


class FakeAlpaca:
    def __init__(self, cash=1000.0, number="PA-EXP"):
        self.cash, self.number = cash, number
        self.orders_, self.qty, self.sent = [], {}, []

    def account(self):
        eq = self.cash + sum(q * 50 for q in self.qty.values())
        return {"cash": str(self.cash), "equity": str(eq), "account_number": self.number, "status": "ACTIVE"}

    def positions(self):
        return [{"symbol": s, "qty": str(q)} for s, q in self.qty.items() if q > 1e-9]

    def orders(self, after):
        return list(self.orders_)

    def market_order(self, symbol, side, cid, *, notional=None, qty=None):
        self.sent.append((symbol, side, cid, notional, qty))
        self.orders_.append({"client_order_id": cid, "symbol": symbol, "side": side, "status": "new", "filled_qty": "0",
                             "notional": notional, "qty": qty, "submitted_at": "2026-12-01T13:00:00Z"})
        return {"id": cid}

    def fill_all(self, price=50.0):
        for o in self.orders_:
            if o["status"] == "new":
                q = o["qty"] if o["qty"] is not None else o["notional"] / price
                o.update(status="filled", filled_qty=str(q), filled_at="2026-12-01T14:31:00Z")
                sign = 1 if o["side"] == "buy" else -1
                self.qty[o["symbol"]] = self.qty.get(o["symbol"], 0) + sign * q
                self.cash -= sign * q * price

    def you(self, symbol, side, qty, price=50.0):
        """An order you place yourself in the Alpaca app."""
        self.orders_.append({"client_order_id": "web-123", "symbol": symbol, "side": side, "status": "filled",
                             "filled_qty": str(qty), "filled_at": "2026-12-02T15:00:00Z"})
        sign = 1 if side == "buy" else -1
        self.qty[symbol] = self.qty.get(symbol, 0) + sign * qty
        self.cash -= sign * qty * price


@pytest.fixture
def conn(tmp_path):
    return db.connect(db.init_db(tmp_path / "e.db"))


@pytest.fixture
def c():
    return _closes()


def _flat(c):
    """Prices at 50 for the last week so trade sizes are easy to check; ranking uses the history before it."""
    c = c.copy()
    c.loc["2026-11-24":] = 50.0
    return c


# --- the rules -------------------------------------------------------------------------------------------------------

def test_rules_pick_the_same_stocks_as_the_backtest(c):
    spec = importlib.util.spec_from_file_location("t", ROOT / "research" / "strategy_tournament.py")
    t = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(t)
    w_mom, w_lowv = t.weights_mom(c, SYMS), t.weights_lowv(c, SYMS)
    for d in list(w_mom)[-6:]:
        assert set(strategies.targets("MOM", c, d)) == set(w_mom[d].index)
        assert set(strategies.targets("LOWV", c, d)) == set(w_lowv[d].index)


def test_signal_is_the_previous_months_last_close(c):
    assert strategies.signal_day(c.index, date(2026, 12, 1)) == pd.Timestamp("2026-11-30")
    assert strategies.signal_day(c.index, date(2026, 11, 24)) == pd.Timestamp("2026-10-30")


def test_momentum_skips_the_last_month(c):
    c2 = c.copy()
    d = pd.Timestamp("2026-10-30")
    i = c.index.get_loc(d)
    c2.iloc[i - 20:, c2.columns.get_loc("S00")] *= 5                  # a huge jump in the last month only
    assert strategies.ranking("MOM", c2, d) == strategies.ranking("MOM", c, d)


# --- placing -----------------------------------------------------------------------------------------------------------

def test_first_run_buys_ten_stocks_with_the_real_cash(conn, c):
    a = FakeAlpaca()
    ex.step("MOM", a, _flat(c), date(2026, 11, 24), conn, datetime(2026, 11, 24, 8))
    buys = [x for x in a.sent if x[1] == "buy"]
    assert len(buys) == 10 and all(x[2].startswith("tx-mom-202611-buy-") for x in buys)
    assert sum(x[3] for x in buys) <= 999.0 + 0.1 and min(x[3] for x in buys) > 99
    assert ex.step("MOM", a, _flat(c), date(2026, 11, 25), conn, datetime(2026, 11, 25, 8)) == []   # month done
    assert len(a.sent) == 10


def test_next_month_sells_first_then_buys_after_the_sells_fill(conn, c):
    a = FakeAlpaca()
    f = _flat(c)
    ex.step("LOWV", a, f, date(2026, 11, 24), conn, datetime(2026, 11, 24, 8))
    a.fill_all()
    held = set(a.qty)
    noisy = f.copy()
    noisy.loc["2025-12-01":"2026-11-30", sorted(held)[0]] *= 1 + 0.2 * np.sin(np.arange(
        len(noisy.loc["2025-12-01":"2026-11-30"])))            # one holding turns jumpy -> leaves the calm 10
    a.sent.clear()
    ex.step("LOWV", a, noisy, date(2026, 12, 1), conn, datetime(2026, 12, 1, 8))
    assert a.sent and all(x[1] == "sell" for x in a.sent)                # sells only, at premarket
    n = len(a.sent)
    ex.step("LOWV", a, noisy, date(2026, 12, 1), conn, datetime(2026, 12, 1, 9, 45))
    assert len(a.sent) == n                                               # still waiting for the fills
    a.fill_all()
    ex.step("LOWV", a, noisy, date(2026, 12, 1), conn, datetime(2026, 12, 1, 10))
    assert any(x[1] == "buy" for x in a.sent[n:])
    assert sorted(held)[0] not in a.qty or a.qty[sorted(held)[0]] < 1e-9


def test_a_stock_you_sell_is_never_bought_back_and_the_next_one_replaces_it(conn, c):
    a = FakeAlpaca()
    f = _flat(c)
    ex.step("MOM", a, f, date(2026, 11, 24), conn, datetime(2026, 11, 24, 8))
    a.fill_all()
    first = strategies.targets("MOM", f, pd.Timestamp("2026-11-30"))
    mine = first[0]
    a.you(mine, "sell", a.qty[mine] / 2)                                   # you sell half
    a.sent.clear()
    ex.step("MOM", a, f, date(2026, 12, 1), conn, datetime(2026, 12, 1, 8))
    a.fill_all()
    ex.step("MOM", a, f, date(2026, 12, 1), conn, datetime(2026, 12, 1, 10))
    assert all(x[0] != mine for x in a.sent)                               # never sold or bought by the agent
    nxt = strategies.ranking("MOM", f, pd.Timestamp("2026-11-30"))[10]
    assert any(x[0] == nxt and x[1] == "buy" for x in a.sent)
    b = ex.book(a.orders_, a.positions(), "MOM")
    assert mine in b.blocked and mine in b.yours and mine not in b.agent_qty


def test_your_own_buy_is_left_alone(conn, c):
    a = FakeAlpaca(cash=1500)
    a.you("S00", "buy", 10)                                                # $500 of your own
    ex.step("MOM", a, _flat(c), date(2026, 11, 24), conn, datetime(2026, 11, 24, 8))
    assert not any(x[0] == "S00" and x[1] == "sell" for x in a.sent)
    b = ex.book(a.orders_, a.positions(), "MOM")
    assert b.yours == {"S00": 10.0}


def test_an_order_you_cancel_is_not_sent_again(conn, c):
    a = FakeAlpaca()
    ex.step("MOM", a, _flat(c), date(2026, 11, 24), conn, datetime(2026, 11, 24, 8))
    a.orders_[0]["status"] = "canceled"
    cancelled = a.orders_[0]["client_order_id"]
    conn.execute("DELETE FROM meta WHERE key = 'exp:MOM:202611:done'")
    conn.commit()
    ex.step("MOM", a, _flat(c), date(2026, 11, 24), conn, datetime(2026, 11, 24, 10))
    assert [x[2] for x in a.sent].count(cancelled) == 1
    assert any("cancelled" in n for n in ex.book(a.orders_, a.positions(), "MOM").notes)


def test_failed_order_is_retried_then_given_up(conn, c):
    a = FakeAlpaca()
    calls = []
    def boom(symbol, side, cid, **k):
        calls.append(cid)
        raise alpaca.AlpacaError("asset not fractionable")
    a.market_order = boom
    for h in (8, 9, 10, 11):
        ex.step("MOM", a, _flat(c), date(2026, 11, 24), conn, datetime(2026, 11, 24, h))
    assert len(calls) == 10 * ex.MAX_FAILS                                  # 3 tries per order, then stop
    assert db.get_meta(conn, "exp:MOM:202611:done")


# --- safety and the scheduler ------------------------------------------------------------------------------------------

def _cfg():
    return load_config()


def test_keys_from_the_main_account_never_trade(conn, c, monkeypatch):
    monkeypatch.setattr(ex, "ready", lambda e: True)
    main = FakeAlpaca(number="PA-MAIN")
    clients = {"MOM": FakeAlpaca(number="PA-MAIN"), "LOWV": FakeAlpaca(number="PA-LOWV")}
    bars = {s: pd.DataFrame({"close": _flat(c)[s]}) for s in SYMS} | {"SPY": pd.DataFrame({"close": _flat(c)["S00"]})}
    monkeypatch.setattr(ex, "TRADED_STOCKS", SYMS)
    out = ex.run_all(_cfg(), conn, bars, date(2026, 11, 24), datetime(2026, 11, 24, 8), "premarket", False,
                     main_client=main, make_client=clients.__getitem__)
    assert clients["MOM"].sent == [] and "MAIN paper account" in db.get_meta(conn, "exp:MOM:problem")
    assert len(clients["LOWV"].sent) == 10 and "MOM blocked" in out


def test_dry_run_places_nothing(conn, c, monkeypatch):
    monkeypatch.setattr(ex, "ready", lambda e: True)
    monkeypatch.setattr(ex, "TRADED_STOCKS", SYMS)
    clients = {"MOM": FakeAlpaca(number="A"), "LOWV": FakeAlpaca(number="B")}
    bars = {s: pd.DataFrame({"close": _flat(c)[s]}) for s in SYMS} | {"SPY": pd.DataFrame({"close": _flat(c)["S00"]})}
    ex.run_all(_cfg(), conn, bars, date(2026, 11, 24), datetime(2026, 11, 24, 8), "premarket", True,
               make_client=clients.__getitem__)
    assert clients["MOM"].sent == clients["LOWV"].sent == []


def test_experiment_client_uses_its_own_keys_and_only_the_paper_host(monkeypatch):
    got = []
    monkeypatch.setattr(secrets, "get_secret", lambda n: got.append(n) or "X")
    calls = []
    cl = ex.client_for("LOWV", lambda m, u, h, b: calls.append(u) or (200, b'{"cash": "1000"}'))
    cl.account()
    assert got == ["alpaca_exp_lowv_key", "alpaca_exp_lowv_secret"]
    assert calls == ["https://paper-api.alpaca.markets/v2/account"]


def test_weekly_section_reports_each_experiment(conn, c, monkeypatch):
    monkeypatch.setattr(ex, "ready", lambda e: True)
    a = FakeAlpaca()
    ex.step("MOM", a, _flat(c), date(2026, 11, 24), conn, datetime(2026, 11, 24, 8))
    a.fill_all()
    ex.save_close(conn, "MOM", a, date(2026, 11, 27))
    bars = {"SPY": pd.DataFrame({"close": c["S00"]})}
    cfg = _cfg().model_copy(update={"experiments": (_cfg().experiments[0],)})
    lines = ex.weekly_lines(cfg, conn, bars, datetime(2026, 11, 28, 9), make_client=lambda i: a,
                            main_since=lambda d: 0.01)
    text = " ".join(l.text for l in lines)
    assert "Stock momentum experiment" in text and "since 2026-11-24" in text and "main paper account +1.0%" in text
    assert "holds 10" in text and "FAILED the pass bar" in text
