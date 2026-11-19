from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

from tradeagent import macro
from tradeagent.config import load_config

NOW = datetime(2026, 11, 19, 15, 0, tzinfo=timezone.utc)


@pytest.fixture(scope="module")
def cfg():
    return load_config()


def item(title, pub, hours_ago=1):
    return macro.Item(title, pub, NOW - timedelta(hours=hours_ago))


def test_factor_keywords():
    assert macro.factor_of("Fed holds interest rates steady", ["rates_fed", "politics_trade"]) == "rates_fed"
    assert macro.factor_of("White House widens chip export controls", ["rates_fed", "politics_trade"]) == "politics_trade"
    assert macro.factor_of("Apple unveils new iPhone", ["rates_fed", "politics_trade"]) is None


def test_two_publishers_confirm(cfg):
    items = [item("Court backs small businesses on tariff refunds", "ProPublica"),
             item("Court backs small business owners for tariff refunds", "The Guardian", 2)]
    (st,) = macro.group_stories(items, cfg, NOW)
    assert st.confirmed(cfg) and st.publishers == {"ProPublica", "The Guardian"}


def test_single_source_is_held(cfg):
    rep = macro.run_once([item("New tariffs on European cars announced", "Blog A")], ["VTI"], cfg, NOW)
    assert rep.confirmed == [] and len(rep.held) == 0   # names no holding's sector or market -> not relevant
    rep = macro.run_once([item("New tariffs on chips hit semiconductor makers", "Blog A")], ["NVDA"], cfg, NOW)
    assert rep.confirmed == [] and len(rep.held) == 1   # relevant but only one source -> held


def test_official_plus_one_news_confirms(cfg):
    items = [item("Minutes of the Federal Open Market Committee, October 27-28", "Federal Reserve"),
             item("Federal Open Market Committee minutes show split over rate hike", "CNBC", 3)]
    stories = macro.group_stories(items, cfg, NOW)
    assert len(stories) == 1 and stories[0].confirmed(cfg) and stories[0].headline.official
    lone = macro.group_stories(items[:1], cfg, NOW)
    assert not lone[0].confirmed(cfg)                    # official alone is one source


def test_same_publisher_twice_does_not_confirm(cfg):
    items = [item("Fed signals rate hike could come in December", "CNBC"),
             item("Fed signals a rate hike may come in December", "CNBC", 2)]
    (st,) = macro.group_stories(items, cfg, NOW)
    assert not st.confirmed(cfg)


def test_old_items_ignored(cfg):
    items = [item("Fed signals rate hike in December", "CNBC", 100), item("Fed signals rate hike in December", "Reuters", 101)]
    assert macro.group_stories(items, cfg, NOW) == []


def test_relevance_rules():
    trade = macro.Story("politics_trade", [item("US widens export controls on chips to China", "Reuters")])
    assert macro.relevant_holdings(trade, ["NVDA", "PG", "VTI"]) == ["NVDA"]
    market = macro.Story("politics_trade", [item("Stocks fall as new tariffs hit Wall Street", "AP")])
    assert "VTI" in macro.relevant_holdings(market, ["VTI", "PG"])
    fed = macro.Story("rates_fed", [item("Fed raises interest rates", "AP")])
    assert macro.relevant_holdings(fed, ["PG", "VTI"]) == ["PG", "VTI"]


def test_rate_sensitivity_recovers_known_beta(cfg):
    rng = np.random.default_rng(1)
    idx = pd.bdate_range("2024-01-01", periods=600)
    dy = pd.Series(rng.normal(0, 0.05, len(idx)), index=idx)
    yld = 4 + dy.cumsum()
    ret = -0.04 * dy + rng.normal(0, 0.004, len(idx))        # -0.4% per +0.10 pt
    px = pd.DataFrame({"close": 100 * (1 + ret).cumprod()}, index=idx)
    s = macro.rate_sensitivity(px, yld, "X", cfg)
    assert s.measured and s.per_10bp == pytest.approx(-0.004, abs=0.0006)
    noise = pd.DataFrame({"close": 100 * (1 + pd.Series(rng.normal(0, 0.01, len(idx)), index=idx)).cumprod()})
    assert not macro.rate_sensitivity(noise, yld, "Y", cfg).measured


def test_fed_change_days_and_impact():
    idx = pd.bdate_range("2024-01-01", periods=40)
    tgt = pd.Series([5.5] * 10 + [5.25] * 20 + [5.5] * 10, index=idx)
    days = macro.fed_change_days(tgt)
    assert days["cut"] == [idx[10]] and days["hike"] == [idx[30]]
    px = pd.DataFrame({"close": np.linspace(100, 140, 40)}, index=idx)
    f = macro.fed_move_impact(px, days["cut"], load_config(), "cut")
    assert f.n == 1 and f.median == pytest.approx(0.0, abs=0.01) and not f.measured   # 1 event: never measured


def test_reported_stories_not_repeated(cfg):
    items = [item("Court backs small businesses on tariff refunds for retail", "ProPublica"),
             item("Court backs small business owners on tariff refunds for retail", "The Guardian", 2)]
    rep = macro.run_once(items, ["WMT"], cfg, NOW)
    assert len(rep.confirmed) == 1
    key = macro.story_key(rep.confirmed[0][0])
    assert macro.run_once(items, ["WMT"], cfg, NOW, already_reported=[key]).confirmed == []


def test_publisher_names_trimmed_and_broad_match_strict(cfg):
    xml = b"""<rss><channel><item><title>Fed holds rates - ABC News - Breaking News, Latest News</title>
      <source url="x">ABC News - Breaking News, Latest News</source><pubDate>Thu, 19 Nov 2026 12:00:00 GMT</pubDate></item></channel></rss>"""
    (it,) = macro._parse_rss(xml, "Google News")
    assert it.publisher == "ABC News"
    deal = macro.Story("politics_trade", [item("Trump says US trade deal with Thailand to be signed soon", "Reuters")])
    assert macro.relevant_holdings(deal, ["VTI", "QQQ"]) == []      # no market words -> not a broad-fund story


def test_email_lines_show_only_measured_links(cfg):
    fed_story = macro.Story("rates_fed", [item("Fed signals rate hike in December", "CNBC"),
                                          item("Fed signals December rate hike", "Reuters", 2)])
    rep = macro.MacroReport([(fed_story, ["PG", "VTI"])], held=[])
    sens = {"PG": macro.Sensitivity("PG", -0.006, -5.4, 504, True), "VTI": macro.Sensitivity("VTI", -0.001, -1.0, 504, False)}
    lines = macro.email_lines(rep, sens, {}, cfg)
    texts = [l.text for l in lines]
    assert texts[0].startswith("Rates & Fed: Fed signals") and set(lines[0].source.split(" + ")) == {"CNBC", "Reuters"}
    assert any("PG:" in t for t in texts) and any("VTI: no measured link" in t for t in texts)
    nothing = macro.email_lines(macro.MacroReport([(fed_story, ["VTI"])], []), sens, {}, cfg)
    assert [l.text for l in nothing][0].startswith("1 more confirmed macro stor")   # no measured link -> counted, not shown


def test_fed_only_line_names_the_holding(cfg):
    fed_story = macro.Story("rates_fed", [item("Fed signals rate hike", "CNBC"), item("Fed signals a rate hike", "AP", 2)])
    imp = {"MA": [macro.FedImpact("hike", 21, -0.013, 0.71, True)]}
    lines = macro.email_lines(macro.MacroReport([(fed_story, ["MA"])], []), {}, imp, cfg)
    assert any(l.text.strip().startswith("MA: after past Fed hikes") for l in lines)
