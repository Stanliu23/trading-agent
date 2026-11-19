# Build plan (v1, 2026-11-18)

This plan builds the system described in SPEC.md, with the emails laid out in EMAILS.md.
Each phase ends with a **Done when** check. We don't start the next phase until that check passes.

## Build decisions

| Topic | Decision |
|---|---|
| Where code lives | I build on this Mac and push to a new private GitHub repo under your account. The always-on Mac pulls from it. No secrets go in the repo. |
| Vibe-Trading | Used as a dependency pinned at commit `ebc849b`. It is not forked, so we upgrade only when we choose to. |
| Trade ideas | A fixed library of written, backtested setups. The AI picks and explains setups, but the statistics come from the library. A new setup is added only after it passes a backtest and you approve it. |
| Small account | Fractional shares confirmed, so positions are sized in dollars. |
| Go-live | A 2-week shadow run first. It uses real data, every email is marked SHADOW, and you don't act on them. |

## Phase 0: your prerequisites (start now, in parallel)

1. **Ask Schwab whether a Schwab International account can register for the Trader API** (individual access at developer.schwab.com). I couldn't confirm this online. If it can, register an app; I'll give you the exact callback URL in Phase 2.
2. ~~Check fractional shares~~ **Done 2026-11-18:** the trade ticket offers buying in dollars.
3. **Get a free Finnhub API key** at finnhub.io, then store it with `uv run tradeagent set-secret finnhub_api_key`. It's needed by Phase 4.
4. **Create the agent's Gmail:** a new account with 2-Step Verification turned on, then an app password. It sends to your Outlook address.
5. **Set up the always-on Mac:**
   - your macOS user stays logged in;
   - it never sleeps;
   - "Start up automatically after a power failure" is on;
   - Python 3.11+, git and gh are installed;
   - Claude Code is installed and logged in (you'll do this at deploy time).

## Phase 1: project skeleton

- Private repo `trading-agent`.
- `config.yaml` holds every approved number: buckets, risk caps, tiers, stars, triggers and schedule.
- `config.local.yaml` holds the email addresses and is never committed.
- Account login tokens and the Gmail app password are stored in the macOS Keychain.
- A SQLite database records snapshots, triggers, recommendations, sent emails and errors.
- The US market calendar (holidays and half days) is reused from Vibe-Trading.
- A `doctor` command checks every prerequisite.

**Done when:** tests pass and `doctor` reports what is still missing.

## Phase 2: account reader (needs the Schwab answer)

- **Plan A, Schwab API:**
  - The HTTP client allows read calls only. A test proves that any order or write call fails before it reaches the network.
  - There is a weekly login command, and a reminder email goes out on day 6.
- **Plan B, CSV files** (if international accounts can't use the API):
  - You export positions and transactions from Schwab into a folder that the agent watches. Vibe-Trading already reads Schwab trade CSVs.
  - Prices then come from Yahoo through Vibe-Trading's loaders.
  - The trade-off: account data is only as fresh as your last export.
- **Both plans:**
  - Deposits are detected from transactions.
  - Each position is tagged to a bucket by the recommendation it came from. Anything untagged is put to you.
  - Fractional quantities are supported.

**Done when:** the snapshot matches the Schwab app to the cent.

## Phase 3: email pipeline (needs the Gmail app password)

- Gmail sends HTML plus a plain-text copy, using the layouts in EMAILS.md.
- Source tags are added to numbers.
- Duplicates are suppressed, and urgent emails have a daily cap.

**Done when:** four sample emails arrive in your Outlook inbox and you approve how they look on your phone.

## Phase 4: trigger rules (no AI)

- Every rule is set in `config.yaml` with an exact threshold.
- A price fetcher pulls from Yahoo and cross-checks Finnhub. If they disagree by more than 1%, the price is marked unconfirmed.
- We replay the last 6 months of prices and count how often each rule would have fired. Rules that fire too often get adjusted.

**Done when:** you approve the replay report (alerts per week, per rule).

## Phase 5: setup library and risk engine

**Status (2026-11-18):** built and backtested, 47 tests pass. Waiting for your approval of `docs/SETUP_STATS.md`.
Vibe-Trading's engine has no per-trade stops, so our own per-trade simulator produces the trade results. Vibe-Trading supplies the price data.

- 4–6 setups:
  - 2 long-term (for example quality/value and broad-market ETF accumulation);
  - 2–4 short-term (for example trend pullback, post-earnings drift and ETF mean reversion).
- Each setup is backtested with Vibe-Trading's engine on US stocks and ETFs from 2015 to 2025, keeping the last 2 years out of the fit to test on.
- Tier and star calculators, as defined in the spec.
- Position sizing under the aggressive profile: 3% of a $300 account is a $9 maximum loss at the stop, and $4.50 for Tier 3. It also checks room left in each bucket and the drawdown pause (25% aggressive, 15% moderate).
- Splitting monthly deposits between the buckets.
- Unit tests that compare the math against hand-calculated examples.

**Done when:** you approve the table of setup statistics and all math tests pass.

## Phase 6: AI analyst

- Vibe-Trading's local API server runs in the background, using your Claude Code login as the model.
- Each trigger type has one prompt. The output is structured, every number goes through the evidence check, and there is a daily cap on AI runs.
- News comes from Yahoo Finance headlines for each holding, plus SEC filings.
- Measured impact uses at least 10 similar past events. We build this tool ourselves because the repo has none for US stocks.

**Done when:** 5 past triggers replayed end to end produce emails in which every number has a source.

## Phase 7: reports

- The premarket update, daily digest and Saturday report.
- Each holding's move is split into market, sector and stock-specific parts, using SPY and the sector's ETF as the yardsticks.
- The scorecard and the cause labels (Calculation, Decision, System, Expected variance).
- The check that flags any cause seen 3 times in 4 weeks.

**Done when:** a weekly report built from replayed weeks reads correctly to you.

## Phase 8: deploy and 2-week shadow run

- Push to the repo. On the always-on Mac you pull it, log in to Claude Code and run `doctor`, and then the scheduled jobs are installed.
- For 2 weeks every email is marked SHADOW. We review the logs together.

**Done when:** 2 weeks pass with no missed runs and you approve going live.

## Phase 9: go live

- Remove the SHADOW marking.
- Write a one-page guide covering the weekly Schwab login, what to do if the Mac was off, and how to change a setting.

## Order and blockers

Phases 1, 4 and 5 don't depend on Schwab or Gmail, so they can start right away.
Phase 2 waits on Schwab's answer and Phase 3 waits on the Gmail app password.
Phase 8 needs you at the always-on Mac.
