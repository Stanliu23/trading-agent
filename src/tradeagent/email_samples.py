"""Four sample emails (made-up tickers AAAA/BBBB/CCCC) for checking layout on your phone."""

from __future__ import annotations

from tradeagent.emailer import ActionBox, Card, Email, Footer, Line, Section, Table, stars_text, subject_line
from tradeagent.setups.library import get

SRC = "sample"


def _card() -> Card:
    return Card(tier=2, stars=4, action="BUY", symbol="AAAA", bucket="short-term",
                size="$75 = 25.0% of account", entry="Entry ≤ $84.50", stop="$79.40 (−6.0%)",
                target="$93.00 (+10.1%)", thesis_rule=None, max_loss="$4.53 = 1.5% of account at stop",
                funding="Sell $75 of BIL first (short-term bucket's parked cash)",
                odds="741 past trades: 50% positive, avg +0.98%, 1 in 20 worse than −6.3%", odds_source="setup S2",
                why_buy=get("S2").logic, why_buy_source="setup S2",
                why="Closed at a 52-week high on 1.9× normal volume, above its 200-day average", why_source=SRC,
                stars_detail="Edge 4 · Confidence 5 · Fit 3")


def _tier3_card() -> Card:
    return Card(tier=3, stars=3, action="BUY", symbol="DDDD", bucket="short-term",
                size="$30 = 10.0% of account", entry="Entry ≤ $212.00", stop="$197.10 (−7.0%)",
                target="$241.80 (+14.1%)", thesis_rule=None, max_loss="$2.10 = 0.7% of account at stop (Tier 3: half-size)",
                funding="Sell $30 of BIL first", odds="90 past trades: 56% positive, avg +1.41%, 1 in 20 worse than −7.1%",
                odds_source="setup S4", why_buy=get("S4").logic, why_buy_source="setup S4",
                why="Opened 5.2% above yesterday's close on 3.4× volume after earnings, closed in the top 20% of its range",
                why_source=SRC, stars_detail="Edge 5 · Confidence 2 · Fit 3")


def _lt_card() -> Card:
    return Card(tier=2, stars=4, action="BUY", symbol="VTI", bucket="long-term", size="$75 = 25.0% of account (position cap)",
                entry="at the open", stop=None, target=None,
                thesis_rule="never on price noise; only a measured thesis break",
                max_loss="no stop: long-term holding",
                funding="from this month's deposit (long-term share $100; the other $25 waits in BIL)",
                odds="567 three-year windows since 2005: 92% positive, 1 in 20 worse than −13.8%",
                odds_source="setup L1", why_buy=get("L1").logic, why_buy_source="setup L1",
                why="Long-term share is 35%; this deposit tops it up toward 40%",
                why_source=SRC, stars_detail="Edge 4 · Confidence 2 · Fit 5")


def footer() -> Footer:
    return Footer(data_as_of="16:30 ET, Nov 18 (sample)", login_days_left=4, account_source="hypothetical account")


def urgent(shadow: bool) -> Email:
    return Email("urgent", subject_line("urgent", ["SELL BBBB", "stop hit", "~$103", "act before close"], shadow),
                 Line("BBBB hit its stop at $41.20 (−6.0% from entry) at 10:45 ET.", SRC, "strong"),
                 [Section("Action", [ActionBox("SELL BBBB · short-term bucket",
                                               [Line("Sell all 2.5 shares. Estimated proceeds $103; they go to BIL.", SRC)])]),
                  Section("Why", [Line("Stop rule from the original recommendation (Nov 4, Tier 2 ★★★☆☆)", SRC),
                                  Line("Drop is a 2.8σ move vs its own 60-day daily range", SRC),
                                  Line("No measured-impact news found; sector ETF down 0.4% only", SRC)]),
                  Section("If you don't act", [Line("Loss so far: −$6.60 = 2.2% of account. Holding past the stop breaks the 2% risk rule.", SRC, "down")])],
                 footer())


def premarket(shadow: bool) -> Email:
    return Email("premarket", subject_line("premarket", ["Wed Nov 19", "$300.42", "1 action"], shadow),
                 Line("1 action for today: buy AAAA at the open (details in last night's digest).", SRC, "strong"),
                 [Section("Overnight", [Line("CCCC −2.3% premarket after an 8-K; similar filings moved it a median −3.4% over 5 days.", SRC, "down")]),
                  Section("Today", [Line("AAAA earnings after Thursday's close · BBBB 1.2% from its stop.", SRC)])],
                 footer())


def digest(shadow: bool) -> Email:
    return Email("digest", subject_line("digest", ["Tue Nov 18", "$300.42", "+$1.20 (+0.4%)", "SPY +0.2%", "4 actions"], shadow),
                 Line("4 actions for tomorrow: sell XLF at the open, sell EEEE before the close, buy AAAA and DDDD.", SRC, "strong"),
                 [Section("Account", [Line("Value $300.42 (+$1.20, +0.4%) · SPY +0.2%", SRC, "up"),
                                      Table(["Bucket", "Now", "Target", "Band", ""],
                                            [["Long-term", "35%", "40%", "35–45%", "✓"], ["Short-term", "65%", "60%", "55–65%", "✓"]], SRC),
                                      Line("Cash parked in BIL $120.00 (+$0.40 interest this month) · drop from peak −2.1% (pause at −15%)", SRC)]),
                  Section("Sells for tomorrow (do these first: they free up cash)", [
                      ActionBox("SELL XLF at tomorrow's open · short-term bucket",
                                [Line("Exit signal: closed back above its 20-day average today (setup S3 rule).", SRC),
                                 Line("All 1.2 shares, about $66; proceeds go back to BIL. Trade result so far +1.8%.", SRC, "up")]),
                      ActionBox("SELL EEEE before tomorrow's close · short-term bucket",
                                [Line("Time limit: tomorrow is day 20 of 20 for a breakout trade (setup S2 rule).", SRC),
                                 Line("All 0.4 shares, about $58; proceeds go back to BIL. Trade result so far −1.1%.", SRC, "down")])]),
                  Section("Buys for tomorrow", [Line("Tier 1 (low risk): none qualified today.", tone="muted"),
                                                Line("Tier 2 (medium risk):", tone="heading"), _card(),
                                                Line("Tier 3 (high risk):", tone="heading"), _tier3_card()]),
                  Section("Long-term this month", [_lt_card()]),
                  Section("News on your holdings", [Line("Measured impact: CCCC 8-K (CEO change); past 14 similar events: median −3.4% over 5 days.", SRC),
                                                    Line("Context only, no measured impact: 2 headlines.", tone="muted")]),
                  Section("Watch next", [Line("AAAA earnings Thu after close · BBBB 1.2% from its stop.", SRC)]),
                  Section("System", [Line("Runs 27/27 OK · AI runs today: 2 · S3 switched off (last 20 paper trades −0.08R)", SRC)])],
                 footer())


def weekly(shadow: bool) -> Email:
    return Email("weekly", subject_line("weekly", ["Nov 10–14", "$300.42", "+$3.50 (+1.2%) vs SPY +0.8%", "1 fix needed"], shadow),
                 Line("Up 1.2% this week vs SPY +0.8%; short-term trading is behind the index funds over 3 months (goal check).", SRC, "strong"),
                 [Section("Performance (time-weighted, deposits removed)",
                          [Table(["", "Week", "Month", "Since start"],
                                 [["Account", "+1.2%", "+2.0%", "+4.8%"], ["Long-term", "+0.6%", "+1.1%", "+5.2%"],
                                  ["Short-term", "+1.5%", "+2.6%", "+4.5%"], ["Index funds", "+0.9%", "+1.8%", "+5.0%"]], SRC)]),
                  Section("Fix needed (same cause 3× in 4 weeks)",
                          [Line("Cause: Decision. S3 dips kept falling; 3 of its last 4 trades hit the stop. Proposed: none; the per-setup switch has paused S3.", SRC)]),
                  Section("Why things moved", [Line("AAAA +5.2% = market +0.8 · sector +1.1 · stock-specific +3.3 (earnings beat, measured)", SRC, "up"),
                                               Line("BBBB −6.0% = market +0.8 · sector −1.2 · stock-specific −5.6 (no measured cause)", SRC, "down")]),
                  Section("Recommendation scorecard",
                          [Table(["Recommendation", "Tier/★", "Acted?", "Result", "Within odds?"],
                                 [["BUY AAAA Nov 4", f"2 {stars_text(4)}", "yes", "+4.1%", "yes"],
                                  ["BUY BBBB Nov 4", f"2 {stars_text(3)}", "yes", "−6.0%", "yes (stop)"]], SRC)]),
                  Section("What went well / what went wrong",
                          [Line("✓ Trigger rules caught the BBBB stop the same morning.", SRC, "up"),
                           Line("✗ BBBB: Expected variance (within its odds). Step: entry signal.", SRC, "down")]),
                  Section("Watched on paper", [Line("37 watched stocks: 9 closed paper trades since Nov 19 (review at 30).", SRC)]),
                  Section("Next week", [Line("Deposit expected: ~$250, split $100 long-term / $150 short-term.", SRC)]),
                  Section("System", [Line("Uptime 100% · missed runs 0 · AI runs 11 · Schwab login renewed Nov 12", SRC)])],
                 footer())


ALL = {"urgent": urgent, "premarket": premarket, "digest": digest, "weekly": weekly}
