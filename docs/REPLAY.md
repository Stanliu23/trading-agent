# 6-month replay with a hypothetical account

Replay 2026-05-18 to 2026-11-18: 129 trading sessions. Starting cash $300.00, then $250.00 on the first session of each month. Every recommendation is assumed taken at the next open. Rules: `config.yaml` as approved. No real money.

## The account

- Deposited $1,800.00; ended at **$1,659.68** ($-140.32, -7.8% on money put in).
- **Time-weighted return** (deposits removed): -7.9%, vs SPY -0.6% over the same sessions.
- Largest drop from a peak, time-weighted: -11.7%. (Raw account value: -5.4%, softened by deposits.)
- Switched from aggressive to moderate on 2026-08-03.
- Profile at the end: moderate. Drawdown pause active on 0 sessions.
- Cash sitting idle: 31% of the account on average; 0% at the end.
- Positions open at the end: 10; average open 6.4.
- Long-term share at the end: 32%.

## Short-term trades

- 31 closed trades, 35% winners, total P&L $-145.08.
- Average position $188.24; smallest $31.24; 0 positions under $20.
- Exits: stop 17, signal 9, time 5.

| Setup | Trades | Win rate | P&L |
|---|---|---|---|
| S2 | 12 | 25% | $-68.54 |
| S3 | 17 | 47% | $-59.85 |
| S4 | 2 | 0% | $-16.69 |

## Open positions at the end

| Symbol | Setup | Bucket | Entry | Since |
|---|---|---|---|---|
| VTI | L1 | long-term | $358.71 × 0.2090 | 2026-05-19 |
| QQQ | L1 | long-term | $740.81 × 0.0576 | 2026-06-02 |
| SCHD | L1 | long-term | $31.82 × 2.6244 | 2026-07-02 |
| QQQ | L1 | long-term | $707.42 × 0.0829 | 2026-08-04 |
| VTI | L1 | long-term | $374.75 × 0.1302 | 2026-09-02 |
| SCHD | L1 | long-term | $32.77 × 6.3002 | 2026-10-02 |
| MA | S2 | short-term | $642.43 × 0.5585 | 2026-10-30 |
| XLE | S3 | short-term | $61.38 × 3.3465 | 2026-11-06 |
| PG | S2 | short-term | $171.34 × 1.8604 | 2026-11-17 |
| DIA | S3 | short-term | $505.54 × 0.5066 | 2026-11-18 |

## Signals not taken

112 setup signals fired on the watchlist; reasons some were not taken:

- already held: 40
- below $20 minimum (cash): 15
- earnings before planned exit: 11
- below $20 minimum (bucket_room): 10
- same symbol, lower-ranked setup: 1

## Alerts this account would have produced

| Alert | Count | Per week |
|---|---|---|
| (close-to-close ≥3σ) | 12 | 0.5 |
| digest:2σ move (intraday touch) | 86 | 3.3 |
| digest:bucket drift | 1 | 0.0 |
| digest:new recommendation | 35 | 1.4 |
| urgent:3σ move (intraday touch) | 25 | 1.0 |
| urgent:stop | 17 | 0.7 |

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
