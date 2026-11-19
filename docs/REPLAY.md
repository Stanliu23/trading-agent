# 6-month replay with a hypothetical account

Replay 2026-05-18 to 2026-11-18: 129 trading sessions. Starting cash $300.00, then $250.00 on the first session of each month. Every recommendation is assumed taken at the next open. Rules: `config.yaml` as approved. No real money.

## The account

- Deposited $1,800.00; ended at **$1,787.32** ($-12.68, -0.7% on money put in).
- **Time-weighted return** (deposits removed): +1.8%, vs SPY -0.6% over the same sessions.
- Largest drop from a peak, time-weighted: -3.2%. (Raw account value: -1.9%, softened by deposits.)
- Moderate rules from the start.
- Goal (short-term must beat holding VTI/QQQ/SCHD over 3 months; restart when the paper book recovers): Goal check 2026-08-21: short-term +3.7% vs index funds +4.7% over 63 sessions; new short-term recommendations paused until you approve a restart.
- Profile at the end: moderate. Drawdown pause active on 0 sessions.
- Cash sitting idle: 41% of the account on average; 61% at the end.
- Positions open at the end: 8; average open 6.3.
- Long-term share at the end: 39%.

## Short-term trades

- 15 closed trades, 53% winners, total P&L $-4.80.
- Average position $121.77; smallest $38.43; 0 positions under $20.
- Exits: stop 6, signal 5, time 4.

| Setup | Trades | Win rate | P&L |
|---|---|---|---|
| S2 | 10 | 30% | $-22.30 |
| S3 | 5 | 100% | $17.50 |

## Open positions at the end

| Symbol | Setup | Bucket | Entry | Since |
|---|---|---|---|---|
| VTI | L1 | long-term | $358.71 × 0.2090 | 2026-05-19 |
| QQQ | L1 | long-term | $703.78 × 0.0639 | 2026-05-20 |
| SCHD | L1 | long-term | $31.63 × 2.4822 | 2026-06-02 |
| QQQ | L1 | long-term | $724.82 × 0.1702 | 2026-07-02 |
| VTI | L1 | long-term | $374.41 × 0.2752 | 2026-08-04 |
| SCHD | L1 | long-term | $34.55 × 2.6475 | 2026-09-02 |
| SCHD | L1 | long-term | $32.77 × 2.9704 | 2026-10-02 |
| QQQ | L1 | long-term | $684.39 × 0.1350 | 2026-11-03 |

## Signals not taken

112 setup signals fired on the watchlist; reasons some were not taken:

- goal pause (behind the index funds): 60
- already held: 25
- below $20 minimum (cash): 7
- earnings before planned exit: 4
- same symbol, lower-ranked setup: 1

## Alerts this account would have produced

| Alert | Count | Per week |
|---|---|---|
| (close-to-close ≥3σ) | 12 | 0.5 |
| digest:2σ move (intraday touch) | 90 | 3.5 |
| digest:new recommendation | 15 | 0.6 |
| urgent:3σ move (intraday touch) | 23 | 0.9 |
| urgent:goal missed, short-term paused | 1 | 0.0 |
| urgent:stop | 6 | 0.2 |

## Watchlist alert rates (if every symbol were held)

60 symbols over 129 sessions.

| Measure | Total | Per symbol per month |
|---|---|---|
| 2σ–3σ close-to-close move | 347 | 0.94 |
| ≥3σ close-to-close move | 109 | 0.30 |
| 2σ–3σ intraday touch | 674 | 1.83 |
| ≥3σ intraday touch | 200 | 0.54 |

## Yahoo headline volume (last 7 days, live)

- Median 18 headlines per symbol; max 20 (ABBV). Fetch failed for 0 symbols.
