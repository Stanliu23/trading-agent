# 6-month replay with a hypothetical account

Replay 2026-05-18 to 2026-11-18: 129 trading sessions. Starting cash $300.00, then $250.00 on the first session of each month. Every recommendation is assumed taken at the next open. Rules: `config.yaml` as approved. No real money.

## The account

- Deposited $1,800.00; ended at **$1,792.61** ($-7.39, -0.4% on money put in).
- **Time-weighted return** (deposits removed): +1.1%, vs SPY -0.6% over the same sessions.
- Largest drop from a peak, time-weighted: -3.0%. (Raw account value: -2.0%, softened by deposits.)
- Switched from aggressive to moderate on 2026-08-03.
- Goal (short-term must beat holding VTI/QQQ/SCHD over 3 months): Goal check 2026-08-21: short-term +2.2% vs index funds +4.7% over 63 sessions; new short-term recommendations paused until you approve a restart.
- Profile at the end: moderate. Drawdown pause active on 0 sessions.
- Cash sitting idle: 60% of the account on average; 83% at the end.
- Positions open at the end: 7; average open 5.4.
- Long-term share at the end: 17%.

## Short-term trades

- 17 closed trades, 59% winners, total P&L $-5.96.
- Average position $128.19; smallest $57.36; 0 positions under $20.
- Exits: signal 7, stop 6, time 4.

| Setup | Trades | Win rate | P&L |
|---|---|---|---|
| S2 | 9 | 33% | $-22.48 |
| S3 | 7 | 100% | $25.42 |
| S4 | 1 | 0% | $-8.90 |

## Open positions at the end

| Symbol | Setup | Bucket | Entry | Since |
|---|---|---|---|---|
| VTI | L1 | long-term | $358.71 × 0.1463 | 2026-05-19 |
| QQQ | L1 | long-term | $740.81 × 0.0402 | 2026-06-02 |
| SCHD | L1 | long-term | $31.82 × 1.8390 | 2026-07-02 |
| QQQ | L1 | long-term | $707.42 × 0.0590 | 2026-08-04 |
| VTI | L1 | long-term | $374.75 × 0.1069 | 2026-09-02 |
| SCHD | L1 | long-term | $32.77 × 1.2929 | 2026-10-02 |
| QQQ | L1 | long-term | $684.39 × 0.0587 | 2026-11-03 |

## Signals not taken

112 setup signals fired on the watchlist; reasons some were not taken:

- goal pause (behind the index funds): 60
- already held: 25
- earnings before planned exit: 4
- below $20 minimum (cash): 4
- below $20 minimum (bucket_room): 1
- same symbol, lower-ranked setup: 1

## Alerts this account would have produced

| Alert | Count | Per week |
|---|---|---|
| (close-to-close ≥3σ) | 11 | 0.4 |
| digest:2σ move (intraday touch) | 78 | 3.0 |
| digest:bucket drift | 1 | 0.0 |
| digest:new recommendation | 17 | 0.7 |
| urgent:3σ move (intraday touch) | 21 | 0.8 |
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
