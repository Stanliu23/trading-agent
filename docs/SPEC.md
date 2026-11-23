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
| Market data | Yahoo only (free, unofficial), decided 2026-11-18. The Finnhub cross-check is built in but switched off; setting `market_data.crosscheck: finnhub` turns it on. Without it, a bad Yahoo quote can fire a false alert. Schwab's market data replaces Yahoo if API access is approved. |
| News | A news item counts toward a rating only if similar past events moved the price measurably. Otherwise it is labelled "context, no measured impact". |
| Universe | Liquid US stocks and ETFs. |
| Check rate | Plain code checks every 15 min while the market is open. AI runs only when a rule fires, plus once after the close. |
| Tier 1 | Similar setups lost money ≤ 25% of the time, and 1 in 20 trades did worse than −8% at most (5th-percentile trade; backtest, 5+ years). |
| Sender | A new Gmail used only by the agent, sending to your personal inbox. |

## 2. Account structure

- **Long-term bucket:** holding period 1–5+ years. Target **40%**, band 35–45% (kept 2026-11-19 after the 36-start-date check; 60/40 earned more on average but with deeper drops) (changed 2026-11-18; was 17.5% and earlier 20–30% / 30–40%).
- **Short-term bucket:** holding period 1 week to about 1 month. Target **60%**, band 55–65%.
- Each bucket keeps its own cash. The agent tags every position to one bucket, and you confirm the tag the first time.
- **Funding (approved 2026-11-18):** long-term funds are bought only with new money: the starting balance and each monthly deposit. Money from short-term trades (sales, profits, unused cash) stays in the short-term bucket for new short-term trades. Money is never moved between buckets.
- **Drift:** if the split leaves its band, the digest says so once and shows how the next deposit will be split to close the gap. It never suggests selling one bucket to buy the other.
- **Idle cash → T-bills (approved 2026-11-18):** uninvested cash in either bucket ($20 or more) is parked in the T-bill ETF BIL, and each bucket's BIL is tracked separately. When a trade needs cash, the recommendation says to sell that amount of BIL first. In replays this helped in 10 of 12 cases.
  - **Cash-account catch:** a stock bought with money from a same-day BIL sale shouldn't be sold before that sale settles (next business day), or Schwab may flag a good-faith violation. If a stop is hit on such a position's entry day, the alert says so and suggests waiting until the next session.
  - **Taxes:** withholding on BIL's monthly payouts for a non-US resident isn't modelled. Check with Schwab.
- If a long-term fund is ever sold on a thesis break, the proceeds stay in the long-term bucket, since they started as deposit money.
- **Monthly deposit:** when a new deposit shows up in the Schwab transactions, the agent emails a split. The bucket furthest below target is filled first, then the rest follows 35/65.
- **Long-term sells:** triggered only by a measured thesis break (for example falling earnings estimates, or valuation above its own 10-year range). Price noise alone is never a reason.
- **Short-term trades:** every one has an entry, a stop and a target before it is recommended.

## 2a. Risk profiles

**Start: moderate** (aggressive start skipped 2026-11-18, `profiles.start_profile`). The aggressive column applies only if that is switched back.

| | Aggressive (until the account first reaches $1,000) | Moderate (from then on, even after a dip) |
|---|---|---|
| Max loss per trade at the stop | 3% | 2% |
| Tier 3 max loss | 1.5% | 1% |
| Pause new short-term trades at a drop from peak of | 25% | 15% |
| Order ideas by | expected return after costs | stars |
| Long-term bucket | 35–45% (target 40%) | 35–45% (target 40%) |

**Drawdown is measured time-weighted (fixed 2026-11-18):** the drop from peak uses a performance index with deposits removed (`risk.performance_index_next`). Measured on raw account value, monthly deposits hid real drops, so the pause never fired. New short-term trades resume when the performance index makes a new high.

The evidence bar is the same in both profiles: at least 30 past trades and a positive result on held-out data.
Account value includes deposits. The switch to moderate happens once and is never reversed.

## 2b. The goal: positive income that beats simply holding the index funds (approved 2026-11-18)

- Short-term trading succeeds only if it earns more than the same money held in VTI, QQQ and SCHD (equal-weight). Otherwise it adds risk without adding income.
- **Weekly check** (last session of the week): compare the short-term bucket's time-weighted return over the last 63 sessions (about 3 months; deposits removed) with the index funds.
- **If it's behind:** stop new short-term recommendations and send one urgent email explaining the numbers.
- **Restart rule (approved 2026-11-18):** while paused, the agent keeps recording what it would have recommended (a paper book, no money). At each weekly check, once that paper book is no longer behind the index funds over the same 63 sessions, it emails asking to restart. Trading resumes only after you approve. After a restart, the next pause check waits a full 63 sessions, so the restarted trades are judged on their own results. Open short-term trades still follow their exits. Short-term cash waits in the short-term bucket (it never moves to long-term; see §2).
- No rule can guarantee positive income. This safeguard limits how long losing trading can run.

## 2c. Macro watch on holdings (approved 2026-11-19)

- **Factors:** rates & the Fed, politics & trade. Checked every 15-minute run while you hold anything.
- **Sources:** Fed press releases and FRED (official); Google News (which names each publisher) and Yahoo headlines (news).
- **Two-source rule:** a story is reported only when 2 independent publishers carry it, or 1 official source plus 1 news report. One-source items are held and re-checked each run; they never reach an email. A publisher repeating itself doesn't count twice.
- **Which holdings a story concerns:** rates & Fed stories concern every holding. Politics & trade stories concern holdings they name, or whose sector they mention. Broad funds (VTI, QQQ, SCHD) count only when the story is about the stock market itself.
- **Shown only with a measured link** (your rule: include it if it influences prices):
  - each holding's sensitivity to the 10-year yield over the last 2 years, counted only if |t| ≥ 2;
  - its moves after past Fed hikes and cuts since 2008, under the same measured-impact rule as news.

  At most 3 stories per factor appear, most-reported first. The rest become a one-line count.
- **Politics & trade** has no historical measure yet, so those stories are counted, not shown.

## 2c-2. Macro as a trade input (approved 2026-11-20)

- **Your choices:**
  - macro may only reduce risk (halve or skip a buy, never start one);
  - trust is re-scored automatically every Saturday with fixed rules;
  - the inputs are market stress (VIX, the dollar via UUP, oil via USO) and the confirmed news stories.
- **Rules:** see REPLAY_FINDINGS, "Macro signals as trade inputs". Every score is kept in `macro_scores`, every news story and its 5-session result in `macro_news`, and the Saturday email lists every change.
- **Status 2026-11-20:** nothing is trusted. VIX-high and dollar-surge hurt S2 trades on paper but failed the account check. News logging has started (20 stories per factor needed).

## 2d. AI analyst (Phase 6, 2026-11-19)

- **What the AI does:** it only writes the sentences. The code first builds measured facts, each with a source: the signal in numbers, the setup's odds, the plan, the earnings date, the measured impact. Claude (your local Claude Code login, model `claude-sonnet-5-5`, no tools) writes "Why now" plus up to 3 lines, citing fact IDs.
- **Number check:** any line with a number that isn't in the facts it cites, or that cites an unknown fact, is dropped. If "Why now" fails the check, the fact itself is used word for word.
- **Fallback:** if the AI is off, over its daily cap (10 runs), or unavailable, a fixed template writes the lines from the facts. Recommendations never depend on the AI.
- **Why not Vibe-Trading's own Claude provider:** it passes a `--restricted` flag that the installed Claude Code CLI (2.1.236) rejects. The analyst calls `claude -p` directly with the same isolation flags minus that one, and it's lighter on tokens than the full Vibe-Trading agent loop.

## 2e. Test on Alpaca's paper account (approved 2026-11-19; open-ended since 2026-11-23)

- **Who trades:** the agent places the pretend account's orders in an **Alpaca paper account** (simulated money). Your Schwab account stays read-only and untouched.
- **Only paper can be reached:** the Alpaca connection refuses any address except `paper-api.alpaca.markets`. The live host is blocked in code and by tests, and the agent never deletes or replaces orders.
- **Timing:** buys and exit-signal sells go in at about 08:00 ET, queued for the open. Stops and targets are checked every 15 minutes and sold at market. Time limits sell in the last 20 minutes of the session.
- **You can step in, and your move is final:**
  - an agent order you cancel is never re-sent;
  - a sell you place is never bought back;
  - a buy you place is flagged until you run `tradeagent tag SYMBOL long_term|short_term`. A short-term tag gives it S2's exits (stop 2×ATR, target 4×ATR, 20 sessions); long-term is held.
- **Emails describe the Alpaca account.** The rules-only pretend account keeps running, and the weekly email compares the two.
- **Money:** Alpaca's real paper balance ($1,000 at the start, nothing added). The plan is sized from the balance recorded at the first run, then split 40/60. Cash is Alpaca's actual cash on every run; anything added or removed later counts as short-term. Idle cash is not parked in BIL during the test.
- **Length:** originally 2 weeks; on 2026-11-23 you extended it with no end date. It runs until you stop it. Nothing in the code ends it.
- **To stop:** set `paper_broker.enabled: false` in `config.yaml` on the MacBook and push; the always-on Mac picks it up at its next daily update (after 06:00 ET). From then on the agent places no Alpaca orders and emails go back to the rules-only pretend account. Anything still held in Alpaca stays there; the agent does not sell it.

## 2f. Strategy experiments in their own Alpaca paper accounts (approved 2026-11-23)

Both strategies FAILED the pass bar in the strategy tournament (docs/REPLAY_FINDINGS.md). You chose to run them anyway
as labelled experiments, so they can be watched live. No real money; Schwab untouched; the main paper test unchanged.

- **Stock momentum (MOM):** at the last close of each month, rank the 77 traded stocks by their return from 12 months
  (252 sessions) ago to 1 month (21 sessions) ago; hold the top 10, 10% each.
- **Low volatility (LOWV):** at the last close of each month, rank the 77 by the standard deviation of daily returns over
  the last 252 sessions; hold the 10 calmest, 10% each.
- **Account:** each has its own Alpaca paper account, $1,000, no deposits, the whole account in the strategy (0/100).
  No stops, targets or time limits; a stock leaves only at a monthly rebalance. Idle cash stays cash.
- **Rebalance:** first run of each month on a trading day (normally 08:00 ET on the 1st session): sells first (stocks
  that left the top 10, trims above 10%), then buys once the sells have filled, from Alpaca's actual cash (no margin).
  The first month starts at the experiment's first run, using the previous month's last close.
- **Your moves are final:** a stock you sell there is never traded by the agent in that account again (the next-ranked
  stock takes its place); shares you buy are yours and left alone; an agent order you cancel is not sent again.
- **Emails:** weekly only, a section in the Saturday report: value, change since start vs SPY and vs the main paper
  account, holdings, your moves, any problem.
- **Safety:** paper host only (same guard as 2e); the agent refuses to trade an experiment whose keys open the main paper
  account or another experiment's account. Rules in `strategies.py`, orders in `experiments.py`.
- **To stop one:** set its `enabled: false` under `experiments:` in config.yaml on the MacBook and push.
- **Big-dip D2 slice in the low-volatility account (2026-11-23):** D2 failed its account test; at Stanley's choice it runs in 25% of the low-volatility account (`dip_share: 0.25`), one dip at a time, rules exactly as tested (`library.DIP_D2`, `dip.py`): buy the morning after a stock's first close 30%+ below its 60-day high (deepest first, earnings skip), stop 2.5xATR checked every 15 minutes, sell the morning after a close 3%+ above the buy price, out after 20 sessions, paused by its per-setup switch. Low volatility then holds its 10 stocks at 7.5% each and leaves the slice's cash free. Orders tagged `tx-dip-`; the Saturday report shows the slice separately. The account's total (and learning question Q6) now mixes both strategies.
- **Sector cap on momentum (trial, approved 2026-11-23):** at most 3 of the 10 picks from one GICS sector (`strategies.SECTOR`). It runs while `trials: "2026-11-23-5"` is on and its removal rule has not fired (docs/LEARNING.md part 3); otherwise the uncapped top 10 is used.

## 2g. Learning from the paper accounts (designed 2026-11-23)

A fill tracker logs every agent fill in all three Alpaca paper accounts with the price the simulator assumed, and
nine fixed questions (trading cost, stop fills, signal frequency, your moves, rebalance timing, experiments vs luck,
the per-setup switch, live vs backtest results, missed runs) are answered every Saturday once each has enough cases.
Questions, minimums and pass rules were fixed before any data: docs/LEARNING.md. They measure and report only; the
automatic cost update is designed there and stays off until you approve it.

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

| Tier | Loss rate (backtest) | 5th-percentile trade | Position size |
|---|---|---|---|
| 1 Low risk | ≤ 25% | no worse than −8% | normal |
| 2 Medium | ≤ 40% | no worse than −15% | normal |
| 3 High | > 40% allowed | worse than −15% allowed | smaller: loss at the stop ≤ half the per-trade cap |

The tail measure is the 5th-percentile trade, not the single worst trade, because the worst trade gets worse simply as a setup collects more trades (approved 2026-11-18). The worst trade is still shown for information.

**Stars** are the average of three 0–5 sub-scores, rounded to the nearest whole star. Ties are allowed.

- **Edge:** expected return per unit of risk, on held-out data.
- **Confidence:** sample size, and how consistent the result is across years.
- **Fit:** 5 minus the steps (0.2, 0.4, 0.6, 0.8, 0.9) that the idea's 60-day correlation with your current holdings exceeds. With nothing held, Fit is 5. Room left in the bucket is enforced by sizing, not by Fit.

Score steps (approved 2026-11-18 with the setup table) live in `config.yaml` under `scoring`.

## 4a. Setup library and position rules

- Trade ideas come only from the fixed setups in `src/tradeagent/setups/library.py`. Their statistics are in `docs/SETUP_STATS.md`.
- Short-term setups are tested from 2015 to 2025, with 2024–2025 held out.
- Long-term setups are tested from 2005 to 2025 on **3-year** forward returns. Their held-out period is the last 2 years of entries that have a complete 3-year result.
- Vibe-Trading's backtest engine works on portfolio weights and has no per-trade stops. So per-trade results come from our own simulator (`setups/simulate.py`), with prices from Vibe-Trading's Yahoo loader.
- **Max position:** 25% of account value per position, in both profiles.
- **Min position:** $20. Smaller amounts stay as cash (approved 2026-11-18).
- **Min edge:** a setup is recommended only if it scores at least 2 of 5 on Edge. Today that rules out S1 (approved 2026-11-18).
- **Ties:** ideas that rank equal go to the one least correlated with what you hold, never alphabetically (approved 2026-11-18).
- **Paper-only watch (approved 2026-11-18):** 37 extra large caps (`paper_watch.stocks` in config) are tracked on paper for S2/S4 but never recommended, and never counted by the per-setup switch. Once a setup has 30 closed paper trades on them since 2026-11-19, the weekly report shows watched vs traded and asks whether to add them.
- **L1 ETFs:** VTI, QQQ and SCHD. Each long-term purchase goes to whichever you hold least of, counting all lots. SPY was dropped as a near-duplicate of VTI (approved 2026-11-18).
- **Earnings:** no new short-term *stock* entry if the stock's next earnings date falls on or before the planned exit. If the date is unknown, the entry is blocked. ETFs are exempt.

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
