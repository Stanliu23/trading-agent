from datetime import date, datetime

import numpy as np
import pandas as pd
import pytest

from tradeagent import db, macro_trust as mt


@pytest.fixture
def conn(tmp_path):
    c = db.connect(db.init_db(tmp_path / "m.db"))
    mt.ensure(c)
    return c


def _cond(days, on_every=4):
    c = pd.DataFrame(False, index=days, columns=list(mt.CONDITIONS))
    c.loc[days[::on_every], "VIX high"] = True
    return c


def _trades(days, cond, r_on, r_off):
    return pd.DataFrame({"setup_id": "S2", "signal_day": days,
                         "r": np.where(cond["VIX high"].reindex(days).to_numpy(), r_on, r_off)})


DAYS = pd.bdate_range("2015-01-01", "2026-11-13")


def test_condition_that_hurts_in_both_periods_passes_and_halves():
    c = _cond(DAYS)
    s = {(x.setup_id, x.condition): x for x in mt.score(_trades(DAYS, c, 0.05, 0.30), c, date(2026, 11, 20))}
    assert s[("S2", "VIX high")].passes and s[("S2", "VIX high")].action == "half"
    assert not s[("S2", "Oil shock")].passes and "too few" in s[("S2", "Oil shock")].reason


def test_condition_with_losing_trades_skips():
    c = _cond(DAYS)
    s = {(x.setup_id, x.condition): x for x in mt.score(_trades(DAYS, c, -0.2, 0.30), c, date(2026, 11, 20))}
    assert s[("S2", "VIX high")].action == "skip"


def test_harm_in_only_one_period_fails():
    c = _cond(DAYS)
    t = _trades(DAYS, c, 0.05, 0.30)
    late = (t.signal_day >= "2024-11-20") & c["VIX high"].reindex(t.signal_day).to_numpy()
    t.loc[late, "r"] = 0.5                                   # helps in the last 2 years
    s = {(x.setup_id, x.condition): x for x in mt.score(t, c, date(2026, 11, 20))}
    assert not s[("S2", "VIX high")].passes


def test_switches_on_only_with_account_check_and_off_without_one(conn):
    c = _cond(DAYS)
    sc = mt.score(_trades(DAYS, c, 0.05, 0.30), c, date(2026, 11, 20))
    ch = mt.record(conn, sc, {}, datetime(2026, 11, 21, 9))
    assert mt.active(conn) == {} and any("failed the account check" in x for x in ch)
    ch = mt.record(conn, sc, {("S2", "VIX high"): True}, datetime(2026, 11, 28, 9))
    assert mt.active(conn) == {("S2", "VIX high"): "half"} and ch[0].startswith("ON")
    ch = mt.record(conn, sc, {}, datetime(2026, 12, 5, 9))       # still passes: stays on without re-checking
    assert mt.active(conn) == {("S2", "VIX high"): "half"} and ch == []
    flat = mt.score(_trades(DAYS, c, 0.30, 0.30), c, date(2026, 12, 12))
    ch = mt.record(conn, flat, {}, datetime(2026, 12, 12, 9))
    assert mt.active(conn) == {} and ch[0].startswith("OFF")


def test_multiplier_takes_the_strictest():
    c = _cond(DAYS)
    c["Dollar surge"] = c["VIX high"]
    m = mt.multipliers({("S2", "VIX high"): "half", ("S2", "Dollar surge"): "skip"}, c)
    assert set(m["S2"].unique()) == {0.0, 1.0}


def test_news_factor_earns_trust_and_blocks_buys(conn):
    spy = pd.Series(100.0, index=pd.bdate_range("2026-01-01", "2026-06-30"))
    bars = {"SPY": pd.DataFrame({"close": spy}), "XYZ": pd.DataFrame({"close": spy * np.linspace(1, 0.7, len(spy))})}
    for i in range(25):
        mt.log_story(conn, f"politics_trade:{i}", spy.index[i * 4].date(), "politics_trade", ["XYZ"], ["Reuters", "AP"])
    assert mt.fill_outcomes(conn, bars) == 25
    v = mt.news_trust(conn)["politics_trade"]
    assert v["trusted"] and v["stories"] == 25 and v["negative"] == 1.0
    mt.log_story(conn, "politics_trade:new", date(2026, 11, 19), "politics_trade", ["XYZ"], ["Reuters", "AP"])
    blocked = mt.news_blocked(conn, date(2026, 11, 20), [date(2026, 11, d) for d in (16, 17, 18, 19, 20)])
    assert "XYZ" in blocked


def test_gate_halves_buys_in_the_simulator():
    from tradeagent.config import load_config
    from tradeagent.papertrade import simulate_portfolio
    idx = pd.bdate_range("2023-01-02", "2024-06-28")
    up = pd.Series(np.linspace(50, 120, len(idx)), idx)
    vol = pd.Series(1e6, idx)
    vol.iloc[::7] = 4e6                                          # volume surges so breakouts fire
    df = pd.DataFrame({"open": up, "high": up * 1.01, "low": up * 0.99, "close": up, "volume": vol})
    bars = {"SPY": df, "AAPL": df, "VTI": df, "QQQ": df, "SCHD": df}
    stats = {"S2": {"recommendable": True, "tier": 1, "edge": 3, "confidence": 3, "mean_ret": 0.01},
             "L1": {"tier": 1, "edge": 3, "confidence": 3}}
    cfg = load_config()
    base = simulate_portfolio(bars, cfg, stats, "2024-01-02", "2024-06-28", 1000, 0, {"AAPL": []})
    gated = simulate_portfolio(bars, cfg, stats, "2024-01-02", "2024-06-28", 1000, 0, {"AAPL": []},
                               macro_mult={"S2": pd.Series(0.0, index=idx)})
    assert any(t.setup_id == "S2" for t in base.trades)
    assert gated.blocked["S2 skipped by a trusted macro condition"] > 0
    assert not any(t.setup_id == "S2" for t in gated.trades + gated.open_positions)


def test_failed_account_check_is_reused_for_four_weeks(conn, monkeypatch):
    from tradeagent import macro_rescore
    c = _cond(DAYS)
    for k in ("^VIX", "UUP", "USO"):
        pass
    calls = []
    monkeypatch.setattr(macro_rescore.prices, "daily_bars", lambda *a, **k: ({}, []))
    monkeypatch.setattr(macro_rescore.macro_trust, "conditions", lambda bars: c)
    monkeypatch.setattr(macro_rescore, "past_trades", lambda bars, cfg: _trades(DAYS, c, 0.05, 0.30))
    monkeypatch.setattr(macro_rescore.account, "earnings_dates", lambda *a, **k: {})
    check = lambda *a: calls.append(1) or (False, "worse in most starts")
    from tradeagent.config import load_config
    cfg = load_config()
    macro_rescore.rescore(cfg, conn, datetime(2026, 11, 21, 9), check=check)
    macro_rescore.rescore(cfg, conn, datetime(2026, 11, 28, 9), check=check)
    assert calls == [1]
    macro_rescore.rescore(cfg, conn, datetime(2026, 12, 26, 9), check=check)
    assert calls == [1, 1] and mt.active(conn) == {}
