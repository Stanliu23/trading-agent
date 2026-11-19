# Personal trading agent: structure (v1, approved 2026-11-18)

Built on HKUDS/Vibe-Trading. Status: structure only, nothing implemented.
All defaults were approved on 2026-11-18. Email layouts are agreed in EMAILS.md.

## 1. Decisions already made

| Topic | Decision |
|---|---|
| Account link | Read-only Schwab API connector (new; Vibe-Trading has none). |
| Trading | The agent never places orders. You trade in the Schwab app; it sees the fill on its next read. |
| Shorts | None for now. Recommendations are buy, add, trim, sell or hold. |
| AI model | Your local Claude Code login (Vibe-Trading's `claude_cli` provider). No API bill. |
| Alerts | Urgent signals are emailed immediately. Otherwise a 3-line premarket update (08:00 ET) and a full digest (16:30 ET). HTML, with $ in subject lines. |
| Risk limit | Two profiles (see §2a). **Aggressive** until the account first reaches $1,000: 3% max loss per trade, pause at a 25% drop, ideas ranked by expected return. **Moderate** from then on: 2% per trade, pause at a 15% drop, ranked by stars. |
| News | A news item counts toward a rating only if similar past events moved the price measurably. Otherwise it is labelled "context, no measured impact". |
| Universe | Liquid US stocks and ETFs. |
| Check rate | Plain code checks every 15 min while the market is open. AI runs only when a rule fires, plus once after the close. |
| Tier 1 | Similar setups lost money ≤ 25% of the time, with worst drop ≤ 8% (backtest, 5+ years). |
| Sender | A new Gmail used only by the agent, sending to your personal inbox. |

## 2. Account structure

- **Long-term bucket:** holding period 1–5+ years. Moderate profile: target 35%, band 30–40%. Aggressive profile: target 25%, band 20–30%.
- **Short-term bucket:** holding period 1 week to about 1 month. Moderate: target 65%, band 60–70%. Aggressive: target 75%, band 70–80%.
- Each bucket keeps its own cash. The agent tags every position to one bucket, and you confirm the tag the first time.
- **Drift:** if either bucket leaves its band, the daily digest proposes a rebalance in dollars.
- **Monthly deposit:** when a new deposit shows up in the Schwab transactions, the agent emails a split. The bucket furthest below target is filled first, then the rest follows 35/65.
- **Long-term sells:** triggered only by a measured thesis break (for example falling earnings estimates, or valuation above its own 10-year range). Price noise alone is never a reason.
- **Short-term trades:** every one has an entry, a stop and a target before it is recommended.

## 2a. Risk profiles

| | Aggressive (until the account first reaches $1,000) | Moderate (from then on, even after a dip) |
|---|---|---|
| Max loss per trade at the stop | 3% | 2% |
| Tier 3 max loss | 1.5% | 1% |
| Pause new short-term trades at a drop from peak of | 25% | 15% |
| Order ideas by | expected return after costs | stars |
| Long-term bucket | 20–30% (target 25%) | 30–40% (target 35%) |

The evidence bar is the same in both profiles: at least 30 past trades and a positive result on held-out data.
Account value includes deposits. The switch to moderate happens once and is never reversed.

## 3. The run cycle

1. **Scheduler (launchd on the Mac):** runs every 15 min from 9:30 to 16:00 ET on trading days, a premarket run at 08:00 ET, a close run at 16:30 ET, and a weekly run on Saturday at 09:00 ET.
2. **Snapshot (no AI):** reads balances, positions and transactions through GET-only Schwab calls, and saves a dated snapshot.
3. **Trigger rules (no AI).** Any one of these fires:
   - a stop or target is hit;
   - a move larger than 2σ of the stock's own daily moves;
   - a bucket leaves its band;
   - a new SEC filing on a holding;
   - earnings within 3 days;
   - a deposit is detected;
   - a headline from a trusted source names a holding.

   If nothing fires, the run ends there and uses no tokens.
4. **AI analyst (on trigger only):** Vibe-Trading's agent loop investigates using repo tools and skills (risk-analysis, event-driven, earnings-revision, valuation-model, quant-statistics, backtest). It also reads the news sources you link.
5. **Risk and tier engine (no AI):** sizes each idea against the 2% cap and bucket room, then assigns a tier and stars by the formulas in §4.
6. **Evidence check:** every number in the email must come from a saved tool output, and unsupported claims are removed. This builds on Vibe-Trading's grounding ledger and run cards.
7. **Email:** sent immediately if urgent, otherwise added to the daily digest.
8. **Log:** every recommendation is saved with its inputs, and whether you acted is read from later Schwab transactions.

**Urgent:** a stop or target is hit, a move larger than 3σ, a news item with measured impact, or a recommendation whose entry window is shorter than one day.

## 4. Tiers and stars

All tiers obey the active profile's per-trade cap. A setup qualifies only with **≥ 30 historical trades** and a positive after-cost result on data held out from the fit.

| Tier | Loss rate (backtest) | Worst drop | Position size |
|---|---|---|---|
| 1 Low risk | ≤ 25% | ≤ 8% | normal |
| 2 Medium | ≤ 40% | ≤ 15% | normal |
| 3 High | > 40% allowed | > 15% allowed | smaller: loss at the stop ≤ half the per-trade cap |

**Stars** are the average of three 0–5 sub-scores, rounded to the nearest whole star. Ties are allowed.

- **Edge:** expected return per unit of risk, on held-out data.
- **Confidence:** sample size, and how consistent the result is across years.
- **Fit:** low correlation with what you already hold, and room left in the bucket.

## 5. Weekly report (Saturday 09:00 ET)

1. Account value and return for the week, versus the S&P 500 (SPY), for each bucket.
2. Why each holding moved. Each move is split into market, sector and stock-specific parts, plus any news with a measured impact.
3. Scorecard: last week's recommendations next to what actually happened.
4. What went well and what went wrong. Each item gets one cause:
   - **Calculation:** bad data or a math error.
   - **Decision:** a rule or threshold chose wrong.
   - **System:** a missed run, an expired login or a stale feed.
   - **Expected variance:** the trade followed the rules and lost within its odds. This is not an error.
5. **Recurrence check:** if the same cause shows up 3 or more times in 4 weeks, the report flags "Fix needed" with a proposed change. Rules change only after you approve.

## 6. Hard safety rules

- The Schwab connector has an allow-list of read endpoints only, and no order code exists anywhere. Schwab's token itself can trade, so this rule has to live in our code.
- Tokens are stored in the macOS Keychain.
- Schwab requires a new login about every 7 days. The agent emails a reminder on day 6. While the login is expired, every email shows "account data stale since …".
- The daily digest includes a heartbeat line. If a digest is missing, the Mac or the agent is down.

## 7. Account facts (from you, 2026-11-18)

- Account: Schwab International, currently empty. Starting balance $300.
- Deposits: about $200–300 a month. The date varies, so deposits are detected from Schwab transactions.
- Emails go to your Outlook address. It is kept only in `config.local.yaml`, which is never committed.
- News sources: Yahoo Finance headlines, plus SEC filings (primary sources).
- Fractional shares: confirmed 2026-11-18. The Schwab trade ticket offers a Shares/Dollars choice (checked on VOO).
- Account: Individual brokerage, options level Covered (0).

## 8. Still open

- Whether Schwab International accounts can use the Trader API. If not, the agent reads CSV exports instead (Plan B in BUILD_PLAN.md).
- The agent's Gmail and its app password.
- Build order and progress: see BUILD_PLAN.md.
