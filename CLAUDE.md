# Rules for any Claude session working in this repo

Read by Claude Code on both Macs and by the weekly cloud routine. Stanley's rules; do not bend them.

## Money and accounts
- The agent never trades real money. Schwab is read-only (`schwab.py` guard); `account.allow_orders` stays false.
- Alpaca is paper only (`alpaca.py` guard: paper host, GET/POST). Never add another broker or host.
- Secrets live in the macOS Keychain via `uv run tradeagent set-secret NAME`. Never ask for, print, log or commit one.
- Personal details (email address) stay in the gitignored `config.local.yaml`.

## Branches
- `main` is LIVE: the always-on Mac pulls it every morning at the first run after 06:00 ET and runs it.
  Anything pushed to main trades the paper accounts the next day.
- `ideas` holds the weekly proposals written by the cloud routine "Weekly ideas from GitHub" (research/ideas/).
  It is READ-ONLY for everyone else: never merge, rebase, cherry-pick or check it out to build from, never push to
  it, never copy code from it into main. Only the weekly routine writes it.
- An idea becomes code only after Stanley says, in his own words, "approve idea N from the week of D". It is then
  built and tested on the MacBook, put through the pass bar below, and reaches main only if it passes and Stanley
  pushes it.

## Changing how the agent decides
- Setup rules, scoring, sizing, exits, strategies and splits change only after a backtest whose pass bar was written
  down BEFORE the results (docs/REPLAY_FINDINGS.md), and Stanley's approval. The usual bar: 36 quarterly starts,
  24 months each, design 2015-2023, check 2024-2025, final check 2026; better than today's rules in >= 60% of starts,
  positive median gain, median worst drop no more than 1 point deeper.
- The learning questions in docs/LEARNING.md and their pass rules are fixed; do not edit them after seeing data.

## Which Mac does what
- MacBook (`~/Documents/Claude Code/trading-agent`): fixes, tests and experiments. Always `git fetch` and review
  what is new on origin/main before committing.
- Always-on Mac (`~/trading-agent`): runs the schedule. Do not leave edited files there: uncommitted edits pause the
  daily auto-update. Prefer sending a fix to the MacBook as a patch; if one is pushed from here, say so.
- Dry runs (`--dry-run`) never place orders and never count as the day's real run.

## Where things are written down
docs/SPEC.md (what the agent does), docs/REPLAY_FINDINGS.md (every test and decision), docs/LEARNING.md (fill
tracker and learning questions), docs/DEPLOY.md (setup and day-to-day commands).
