# 6-month replay with a hypothetical account

Replay 2026-05-18 to 2026-11-18: 129 trading sessions. Starting cash $300.00, then $250.00 on the first session of each month. Every recommendation is assumed taken at the next open. Rules: `config.yaml` as approved. No real money.

## The account

- Deposited $1,800.00; ended at **$1,663.15** ($-136.85, -7.6% on money put in).
- **Time-weighted return** (deposits removed): -6.5%, vs SPY -0.6% over the same sessions.
- Largest drop from a peak, time-weighted: -12.1%. (Raw account value: -6.7%, softened by deposits.)
- Switched from aggressive to moderate on 2026-08-03.
- Profile at the end: moderate. Drawdown pause active on 0 sessions.
- Cash sitting idle: 19% of the account on average; 3% at the end.
- Positions open at the end: 10; average open 7.4.
- Long-term share at the end: 27%.

## Short-term trades

- 97 closed trades, 58% winners, total P&L $-128.83.
- Average position $151.45; smallest $1.17; 12 positions under $20.
- Exits: signal 72, stop 17, time 8.

| Setup | Trades | Win rate | P&L |
|---|---|---|---|
| S1 | 77 | 62% | $-45.05 |
| S2 | 9 | 33% | $-33.05 |
| S3 | 10 | 50% | $-50.68 |
| S4 | 1 | 0% | $-0.05 |

## Open positions at the end

| Symbol | Setup | Bucket | Entry | Since |
|---|---|---|---|---|
| SPY | L1 | long-term | $731.08 × 0.1025 | 2026-05-19 |
| QQQ | L1 | long-term | $740.81 × 0.0831 | 2026-06-02 |
| VTI | L1 | long-term | $369.46 × 0.1784 | 2026-07-02 |
| SCHD | L1 | long-term | $33.20 × 1.2092 | 2026-08-04 |
| SCHD | L1 | long-term | $34.55 × 6.3850 | 2026-09-02 |
| LLY | S2 | short-term | $1,391.46 × 0.1641 | 2026-11-02 |
| MA | S2 | short-term | $638.32 × 0.5667 | 2026-11-02 |
| XLE | S3 | short-term | $61.38 × 3.6643 | 2026-11-06 |
| PG | S2 | short-term | $171.34 × 0.8993 | 2026-11-17 |
| DIA | S3 | short-term | $505.54 × 0.3850 | 2026-11-18 |

## Signals not taken

607 setup signals fired on the watchlist; reasons some were not taken:

- no room (cash): 199
- already held: 164
- no room (bucket_room): 79
- earnings before planned exit: 51
- same symbol, lower-ranked setup: 12

## Alerts this account would have produced

| Alert | Count | Per week |
|---|---|---|
| (close-to-close ≥3σ) | 10 | 0.4 |
| digest:2σ move (intraday touch) | 82 | 3.2 |
| digest:bucket drift | 4 | 0.2 |
| digest:new recommendation | 102 | 4.0 |
| urgent:3σ move (intraday touch) | 20 | 0.8 |
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
