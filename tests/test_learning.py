from datetime import date, datetime
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from tradeagent import db, learning as L
from tradeagent.config import load_config

NY = L.NY
DAY = pd.Timestamp("2026-11-23")


@pytest.fixture
def conn(tmp_path):
    return db.connect(db.init_db(tmp_path / "l.db"))


def bar(o=100.0, h=102.0, lo=98.0, c=101.0):
    return pd.Series({"open": o, "high": h, "low": lo, "close": c})


def bars_for(symbol="XYZ", days=None, o=100.0):
    idx = days if days is not None else pd.bdate_range("2026-11-16", "2026-11-27")
    return {symbol: pd.DataFrame({"open": o, "high": o * 1.02, "low": o * 0.98, "close": o * 1.01}, index=idx)}


def order(cid, side, fill, sub="2026-11-23T12:59:00Z", filled="2026-11-23T14:30:05Z", symbol="XYZ", qty=1.0, oid=None):
    return {"id": oid or cid, "client_order_id": cid, "symbol": symbol, "side": side, "status": "filled",
            "filled_qty": str(qty), "filled_avg_price": str(fill), "submitted_at": sub, "filled_at": filled}


# --- assumed prices: the simulator's own conventions ----------------------------------------------------------------

def test_assumed_prices_follow_the_simulator():
    assert L.assumed("entry", "buy", bar(), True) == (100.0, "open", "Q1")
    assert L.assumed("entry", "buy", bar(), False)[2] == ""                      # sent after the open: not counted
    assert L.assumed("stop", "sell", bar(o=95), True, stop=97) == (95.0, "open (gapped below the stop)", "Q2")
    assert L.assumed("stop", "sell", bar(), True, stop=99) == (99.0, "stop", "Q2")
    assert L.assumed("time", "sell", bar(), False) == (101.0, "close", "Q1")
    assert L.assumed("rebalance", "buy", bar(), False)[2] == "Q5"
    assert L.assumed("rebalance", "sell", bar(), True) == (100.0, "open", "Q1")


def test_cost_is_positive_when_worse_for_us():
    assert L.cost_pct("buy", 100.2, 100) == pytest.approx(0.002)
    assert L.cost_pct("sell", 99.8, 100) == pytest.approx(0.002)
    assert L.cost_pct("sell", 100.1, 100) < 0


# --- the fill tracker -----------------------------------------------------------------------------------------------

def test_agent_fills_are_logged_once_yours_never(conn):
    orders = [order("ta-20261123-entry-XYZ-S2", "buy", 100.3), order("web-1", "buy", 100.0, oid="u1")]
    intents = {"ta-20261123-entry-XYZ-S2": {"purpose": "entry"}}
    assert L.record_fills(conn, "main", orders, bars_for(), "ta-", intents) == 1
    assert L.record_fills(conn, "main", orders, bars_for(), "ta-", intents) == 0
    row = conn.execute("SELECT account, purpose, assumed, cost_pct, question FROM fill_log").fetchone()
    assert tuple(row)[:3] == ("main", "entry", 100.0) and row[3] == pytest.approx(0.003) and row[4] == "Q1"


def test_fill_waits_for_its_days_price_bar(conn):
    o = [order("ta-x", "buy", 100.0)]
    early = bars_for(days=pd.bdate_range("2026-11-16", "2026-11-20"))
    assert L.record_fills(conn, "main", o, early, "ta-", {"ta-x": {"purpose": "entry"}}) == 0
    assert L.record_fills(conn, "main", o, bars_for(), "ta-", {"ta-x": {"purpose": "entry"}}) == 1


def test_stop_sell_keeps_the_lot_for_the_stop_question(conn):
    intents = {"ta-e": {"purpose": "entry", "stop": 95.0, "target": 110.0},
               "ta-s": {"purpose": "stop", "lot_ref": "ta-e"}}
    orders = [order("ta-e", "buy", 100.0, sub="2026-11-20T12:59:00Z", filled="2026-11-20T14:30:00Z"),
              order("ta-s", "sell", 94.0, sub="2026-11-23T16:00:00Z", filled="2026-11-23T16:00:02Z")]
    L.record_fills(conn, "main", orders, bars_for(), "ta-", intents)
    r = conn.execute("SELECT assumed, fill, lot_entry, lot_stop, question FROM fill_log WHERE purpose='stop'").fetchone()
    assert tuple(r) == (95.0, 94.0, 100.0, 95.0, "Q2")


def test_experiment_buys_go_to_the_timing_question(conn):
    o = [order("tx-mom-202611-buy-XYZ", "buy", 100.5, sub="2026-11-23T14:45:00Z", filled="2026-11-23T14:45:01Z")]
    L.record_fills(conn, "MOM", o, bars_for(), "tx-mom-")
    assert conn.execute("SELECT question, purpose FROM fill_log").fetchone()[:] == ("Q5", "rebalance")


# --- questions --------------------------------------------------------------------------------------------------------

def _fills(conn, q, costs):
    k = conn.execute("SELECT COUNT(*) FROM fill_log").fetchone()[0]
    conn.executemany("INSERT INTO fill_log(order_id, account, symbol, side, cost_pct, question) VALUES (?,?,?,?,?,?)",
                     [(f"o{q}{k + i}", "main", "XYZ", "buy", c, q) for i, c in enumerate(costs)])
    conn.commit()


def test_cost_question_waits_then_flags_high_costs(conn):
    _fills(conn, "Q1", [0.002] * 29)
    a = L.q1_cost(conn)
    assert a.status == "waiting" and "29 of 30" in a.text and "%" not in a.text           # no peeking
    _fills(conn, "Q1", [0.002 + 0.0001 * i for i in range(30, 33)])
    a = L.q1_cost(conn)
    assert a.status == "flag" and "HIGHER" in a.text


def test_cost_question_never_loosens(conn):
    rng = np.random.default_rng(1)
    _fills(conn, "Q1", list(rng.normal(0.0001, 0.0002, 40)))
    a = L.q1_cost(conn)
    assert a.status == "ok" and ("lower than" in a.text and "never loosens" in a.text or "consistent" in a.text)


def test_stop_question_in_r(conn):
    conn.executemany("INSERT INTO fill_log(order_id, account, symbol, side, assumed, fill, lot_entry, lot_stop, question) "
                     "VALUES (?,?,?,?,?,?,?,?,?)",
                     [(f"s{i}", "main", "XYZ", "sell", 95.0, 94.0 - 0.1 * (i % 3), 100.0, 95.0, "Q2") for i in range(10)])
    conn.commit()
    a = L.q2_stops(conn)
    assert a.status == "flag" and "+0.22R" in a.text                                  # about 1.1 / 5 R extra


def test_rule_exit_stop_target_time_and_open():
    idx = pd.bdate_range("2026-11-02", "2026-11-13")
    close = pd.Series([100, 101, 102, 103, 97, 96, 95, 94, 93, 92], idx, dtype=float)
    df = pd.DataFrame({"open": close, "high": close + 1, "low": close - 1, "close": close})
    entry = idx[0]
    assert L.rule_exit(df, idx[1], entry, stop=95.5)[:3] == (95.5, idx[5], "stop")
    assert L.rule_exit(df, idx[0], entry, target=103.5)[2] == "target"
    assert L.rule_exit(df, idx[0], entry, max_hold=3)[:3] == (102.0, idx[2], "time")
    px, d, why, done = L.rule_exit(df, idx[0], entry)
    assert (px, why, done) == (92.0, "still open (latest close)", False)


def test_your_moves_are_compared_with_the_rule():
    idx = pd.bdate_range("2026-11-02", "2026-11-27")
    close = pd.Series(np.linspace(100, 80, len(idx)), idx)                               # steady fall
    bars = {"XYZ": pd.DataFrame({"open": close, "high": close + 0.5, "low": close - 0.5, "close": close})}
    lot = SimpleNamespace(symbol="XYZ", setup_id="S2", entry_day=idx[0].date(), stop=90.0, target=None, max_hold=20)
    sells = [SimpleNamespace(reason="you", lot=lot, qty=1.0, exit=97.0, exit_day=idx[3].date()) for _ in range(10)]
    a = L.q4_your_moves(SimpleNamespace(closed=sells, yours_cancelled=set()), {}, bars)
    assert a.status == "ok" and "100% beat the rule" in a.text and "your moves helped" in a.text


def test_cancelled_losing_buy_counts_as_helping():
    idx = pd.bdate_range("2026-11-02", "2026-11-27")
    close = pd.Series(np.linspace(100, 80, len(idx)), idx)
    bars = {"XYZ": pd.DataFrame({"open": close, "high": close + 0.5, "low": close - 0.5, "close": close})}
    intents = {f"ta-{i}": {"side": "buy", "symbol": "XYZ", "dollars": 50.0, "session": idx[2].date().isoformat(),
                           "setup_id": "S2", "stop": 95.0, "target": 110.0, "max_hold": 20} for i in range(10)}
    a = L.q4_your_moves(SimpleNamespace(closed=[], yours_cancelled=set(intents)), intents, bars)
    assert "100% beat the rule" in a.text


def test_experiment_inside_the_luck_band(conn):
    spy = pd.Series(np.linspace(600, 606, 12), pd.bdate_range("2026-11-16", "2026-12-01"))
    db_set = lambda k, v: conn.execute("INSERT INTO meta(key, value) VALUES (?, ?)", (k, v))
    db_set("exp:MOM:start", "2026-11-23")
    db_set("exp:MOM:start_equity", "1000")
    conn.executemany("INSERT INTO exp_daily(exp_id, day, equity, cash) VALUES ('MOM', ?, ?, 0)",
                     [(d.date().isoformat(), 1000 + i) for i, d in enumerate(spy.index[5:])])
    conn.commit()
    a = L.q6_luck(conn, {"SPY": pd.DataFrame({"close": spy})}, ["MOM"])[0]
    assert a.status == "ok" and "within luck" in a.text


def test_switch_and_backtest_questions_wait_for_enough_trades():
    t = pd.DataFrame({"setup_id": ["S2"] * 5, "signal_day": pd.bdate_range("2026-11-20", periods=5),
                      "exit": pd.bdate_range("2026-11-25", periods=5), "r": [-1.0] * 5, "closed": True})
    cfg = load_config()
    assert L.q7_switch(t, cfg).status == "waiting"
    assert L.q8_live_vs_backtest(t).status == "waiting"


def test_live_results_far_below_the_backtest_are_flagged():
    n = 40
    t = pd.DataFrame({"setup_id": ["S3"] * n, "signal_day": pd.bdate_range("2026-11-20", periods=n),
                      "exit": pd.bdate_range("2026-11-25", periods=n), "r": [-0.9] * n, "closed": True})
    a = L.q8_live_vs_backtest(t)
    assert a.status == "flag" and "S3" in a.text and "BELOW" in a.text


def test_missed_runs_are_flagged(conn):
    conn.execute("INSERT INTO runs(kind, started_at, status) VALUES ('premarket', '2026-11-23T08:00:00-05:00', 'ok')")
    conn.execute("INSERT INTO runs(kind, started_at, status) VALUES ('close', '2026-11-23T16:30:00-05:00', 'ok')")
    conn.commit()
    ok = L.q9_operations(conn, date(2026, 11, 23), datetime(2026, 11, 23, 18, tzinfo=NY))
    assert ok.status == "ok"
    late = L.q9_operations(conn, date(2026, 11, 24), datetime(2026, 11, 24, 18, tzinfo=NY))
    assert late.status == "flag" and "premarket Nov 24" in late.text and "close Nov 24" in late.text


def test_weekly_section_never_breaks_the_email(conn):
    lines = L.weekly_lines(conn, {}, load_config(), datetime(2026, 11, 28, 9, tzinfo=NY))
    assert len(lines) == 1 and "could not be scored" in lines[0].text


def test_answers_are_stored_every_week(conn):
    out = [L.Answer("Q1", 3, 30, "waiting", "3 of 30"), L.Answer("Q9", 0, None, "ok", "fine")]
    L.store(conn, out, datetime(2026, 11, 28, 9, tzinfo=NY))
    assert conn.execute("SELECT COUNT(*) FROM learning_log").fetchone()[0] == 2
