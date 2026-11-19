# 6-month replay with a hypothetical account

Replay 2026-05-18 to 2026-11-18: 129 trading sessions. Starting cash $300.00, then $250.00 on the first session of each month. Every recommendation is assumed taken at the next open. Rules: `config.yaml` as approved. No real money.

## The account

- Deposited $1,800.00; ended at **$1,777.75** ($-22.25, -1.2% on money put in).
- **Time-weighted return** (deposits removed): -0.0%, vs SPY -0.6% over the same sessions.
- Largest drop from a peak, time-weighted: -4.1%. (Raw account value: -2.0%, softened by deposits.)
- Switched from aggressive to moderate on 2026-08-03.
- Goal (short-term must beat holding VTI/QQQ/SCHD over 3 months): Goal check 2026-08-21: short-term +1.0% vs index funds +4.7% over 63 sessions; new short-term recommendations paused until you approve a restart.
- Profile at the end: moderate. Drawdown pause active on 0 sessions.
- Cash sitting idle: 50% of the account on average; 66% at the end.
- Positions open at the end: 7; average open 5.3.
- Long-term share at the end: 34%.

## Short-term trades

- 16 closed trades, 56% winners, total P&L $-15.41.
- Average position $129.95; smallest $31.24; 0 positions under $20.
- Exits: stop 7, signal 6, time 3.

| Setup | Trades | Win rate | P&L |
|---|---|---|---|
| S2 | 9 | 33% | $-26.17 |
| S3 | 6 | 100% | $19.61 |
| S4 | 1 | 0% | $-8.85 |

## Open positions at the end

| Symbol | Setup | Bucket | Entry | Since |
|---|---|---|---|---|
| VTI | L1 | long-term | $358.71 × 0.2090 | 2026-05-19 |
| QQQ | L1 | long-term | $740.81 × 0.0576 | 2026-06-02 |
| SCHD | L1 | long-term | $31.82 × 2.6244 | 2026-07-02 |
| QQQ | L1 | long-term | $707.42 × 0.0829 | 2026-08-04 |
| VTI | L1 | long-term | $374.75 × 0.4979 | 2026-09-02 |
| SCHD | L1 | long-term | $32.77 × 2.5834 | 2026-10-02 |
| QQQ | L1 | long-term | $684.39 × 0.1204 | 2026-11-03 |

## Signals not taken

112 setup signals fired on the watchlist; reasons some were not taken:

- goal pause (behind the index funds): 60
- already held: 24
- below $20 minimum (cash): 7
- earnings before planned exit: 4
- same symbol, lower-ranked setup: 1

## Alerts this account would have produced

| Alert | Count | Per week |
|---|---|---|
| (close-to-close ≥3σ) | 11 | 0.4 |
| digest:2σ move (intraday touch) | 76 | 2.9 |
| digest:bucket drift | 1 | 0.0 |
| digest:new recommendation | 16 | 0.6 |
| urgent:3σ move (intraday touch) | 21 | 0.8 |
| urgent:goal missed, short-term paused | 1 | 0.0 |
| urgent:stop | 7 | 0.3 |

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
