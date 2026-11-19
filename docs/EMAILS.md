# Email layouts (v2, 2026-11-18)

There are four emails: **Urgent alert**, **Premarket update**, **Daily digest** and **Weekly report**. All of them share the same recommendation card and footer.
Every number, ticker and price below is made-up sample data that only shows the layout.

## Rules for every email

- Format: clean HTML (simple tables, green/red for up/down, star icons), sized for Gmail on a phone. Each email also includes a plain-text copy.
- Subject lines include dollar amounts as well as percentages.

- The most important line comes first. If you read only the subject and the first line, you know what to do.
- Every number has a source tag, e.g. `[schwab 10:45]`, `[bt run-0412]` or `[SEC 8-K]`. The evidence check removes any number without one.
- No adjectives without numbers. Write "fell 4.1%, a 2.6σ move", not "plunged".
- Recommendations always show the tier, the stars, the size in dollars and % of the account, and the most you can lose at the stop.
- If no idea qualifies for a tier, the email says "Tier 2: none qualified today" rather than leaving the tier out.
- Footer on every email: data freshness, days until the Schwab login expires, and "This agent cannot place trades."

## Shared recommendation card

```
[TIER 1 · ★★★★☆]  BUY  AAAA  · long-term bucket
Size      $1,200 = 2.4% of account   Entry ≤ $84.50
Stop      $79.40 (−6.0%)             Target $93.00 (+10.1%)
Max loss  $72 = 0.14% of account at stop
Odds      42 past setups: 78% positive after 20 days, median +3.1%, worst −6.2%   [bt run-0412]
Why now   Earnings estimates up 4.2% in 30 days (3rd percentile of revisions)   [estimates 11-17]
Stars     Edge 4 · Confidence 5 · Fit 3
```

Long-term buys have no fixed stop. In its place they show a thesis-break rule, e.g. "Sell if forward EPS estimate falls > 15% from today."

## 1. Urgent alert (only when time-sensitive)

```
Subject: URGENT · SELL BBBB · stop hit · ~$1,030 · act before close

BBBB hit its stop at $41.20 (−6.0% from entry) at 10:45 ET.   [schwab 10:45]

ACTION
  Sell all 25 shares (short-term bucket). Est. proceeds $1,030.

WHY
  • Stop rule from the original recommendation (Nov 4, Tier 2 ★★★☆☆)
  • Drop is a 2.8σ move vs its own 60-day daily range   [prices 10:45]
  • No measured-impact news found; sector ETF down 0.4% only   [news 10:40]

IF YOU DON'T ACT
  Rule-based loss so far: −$66 = 0.13% of account. Holding past the stop breaks the 2% risk rule.

Data fresh as of 10:45 ET · Schwab login expires in 4 days · This agent cannot place trades.
```

## 2. Premarket update (08:00 ET, 3 lines)

```
Subject: Premarket · Wed Nov 19 · $50,240 · 1 action

Overnight: CCCC −2.3% premarket after 8-K (measured impact: median −3.4% over 5 days).   [SEC 8-K]
Today: AAAA earnings after close · BBBB 1.2% from its stop.
Action: none new since last night's digest.
```

It reuses the snapshot and rules from the overnight runs. The AI runs only if something new fired overnight.

## 3. Daily digest (16:30 ET, after the close)

```
Subject: Daily · Tue Nov 18 · $50,240 · +$201 (+0.4%) · SPY +0.2% · 1 action

1  ACCOUNT
   Value $50,240  (+$201, +0.4%)   SPY +0.2%            [schwab 16:30]
   Long-term  34%  (target 35%, band 30–40%)  ✓
   Short-term 66%  (target 65%, band 60–70%)  ✓
   Cash $3,110 · Drawdown from peak −2.1% (pause at −15%)

2  ACTIONS FOR TOMORROW  (1)
   [recommendation card(s)]

3  RECOMMENDATIONS
   Tier 1: [card] … or "none qualified today"
   Tier 2: …
   Tier 3: …

4  NEWS ON YOUR HOLDINGS
   Measured impact:  CCCC 8-K, CEO change. Past 14 similar events: median −3.4% over 5 days.   [SEC 8-K]
   Context only (no measured impact): 2 items, one line each.

5  WATCH NEXT
   AAAA earnings Thu after close · BBBB 1.2% from its stop

6  SYSTEM
   Runs 27/27 OK · AI runs today: 2 · Schwab login expires in 4 days
```

## 4. Weekly report (Saturday 09:00 ET)

The first screen on a phone shows the summary, performance and any fix needed. The details follow below.

```
Subject: Weekly · Nov 10–14 · $50,240 · +$596 (+1.2%) vs SPY +0.8% · 1 fix needed

SUMMARY (3 lines max)

1  PERFORMANCE
             Week     Month    Since start
   Account   +1.2%    +2.0%    +4.8%
   Long-term +0.6%    …
   Short-term+1.5%    …
   SPY       +0.8%    …

2  FIX NEEDED  (same cause 3× in 4 weeks)
   Cause, evidence, proposed change. Waiting for your approval.

── details below ──

3  WHY THINGS MOVED (top 3 up, top 3 down)
   AAAA +5.2% = market +0.8 · sector +1.1 · stock-specific +3.3 (earnings beat, measured)
   …

4  RECOMMENDATION SCORECARD
   Rec            Tier/★   You acted?  Result    Within odds?
   BUY AAAA 11-04  1 ★★★★   yes         +4.1%     yes
   …

5  WHAT WENT WELL / WHAT WENT WRONG
   ✓ …  step: Trigger rules → caught the BBBB stop same morning
   ✗ …  cause: Calculation | Decision | System | Expected variance   step: <which step>

6  NEXT WEEK
   Earnings on holdings · expected deposit and its split · rebalance if a bucket is out of band

7  SYSTEM
   Uptime, missed runs, AI runs and token use this week
```
