# 6-month replay with a hypothetical account

Replay 2025-11-18 to 2026-11-18: 252 trading sessions. Starting cash $300.00, then $250.00 on the first session of each month. Every recommendation is assumed taken at the next open. Rules: `config.yaml` as approved. No real money.

## The account

- Deposited $3,300.00; ended at **$3,349.05** ($49.05, +1.5% on money put in).
- **Time-weighted return** (deposits removed): +9.6%, vs SPY +11.8% over the same sessions.
- Largest drop from a peak, time-weighted: -6.6%. (Raw account value: -5.8%, softened by deposits.)
- Moderate rules from the start.
- Goal (short-term must beat holding VTI/QQQ/SCHD over 3 months; restart when the paper book recovers): Goal check 2026-02-20: short-term +7.6% vs index funds +8.2% over 63 sessions; new short-term recommendations paused until you approve a restart.; Restart 2026-02-27: paper short-term +12.2% vs index funds +6.3%.; Goal check 2026-05-29: short-term -0.6% vs index funds +11.6% over 63 sessions; new short-term recommendations paused until you approve a restart.; Restart 2026-07-17: paper short-term +11.2% vs index funds +7.8%.; Goal check 2026-10-16: short-term -7.5% vs index funds +3.5% over 63 sessions; new short-term recommendations paused until you approve a restart.
- Profile at the end: moderate. Drawdown pause active on 0 sessions.
- Cash sitting idle: 32% of the account on average; 61% at the end.
- Positions open at the end: 12; average open 9.2.
- Long-term share at the end: 39%.

## Short-term trades

- 47 closed trades, 49% winners, total P&L $-63.47.
- Average position $245.30; smallest $29.99; 0 positions under $20.
- Exits: time 14, stop 13, signal 11, target 9.

| Setup | Trades | Win rate | P&L |
|---|---|---|---|
| S2 | 24 | 46% | $29.28 |
| S3 | 20 | 55% | $-75.99 |
| S4 | 3 | 33% | $-16.76 |

## Open positions at the end

| Symbol | Setup | Bucket | Entry | Since |
|---|---|---|---|---|
| VTI | L1 | long-term | $320.98 × 0.2335 | 2025-11-19 |
| QQQ | L1 | long-term | $608.76 × 0.0739 | 2025-11-20 |
| SCHD | L1 | long-term | $26.60 × 3.7812 | 2025-12-02 |
| QQQ | L1 | long-term | $617.22 × 0.1628 | 2026-01-05 |
| VTI | L1 | long-term | $340.11 × 0.2903 | 2026-02-03 |
| SCHD | L1 | long-term | $30.88 × 3.4018 | 2026-03-03 |
| QQQ | L1 | long-term | $572.74 × 0.1654 | 2026-04-02 |
| VTI | L1 | long-term | $370.87 × 0.4425 | 2026-06-02 |
| SCHD | L1 | long-term | $31.82 × 3.5822 | 2026-07-02 |
| QQQ | L1 | long-term | $707.42 × 0.1267 | 2026-08-04 |
| SCHD | L1 | long-term | $32.77 × 4.4037 | 2026-10-02 |
| VTI | L1 | long-term | $370.27 × 0.2360 | 2026-11-03 |

## Signals not taken

301 setup signals fired on the watchlist; reasons some were not taken:

- below $20 minimum (cash): 93
- already held: 71
- S3 switched off (last 20 paper trades below +0R): 32
- S2 switched off (last 20 paper trades below +0R): 26
- earnings before planned exit: 21
- goal pause (behind the index funds): 9
- same symbol, lower-ranked setup: 2

## Alerts this account would have produced

| Alert | Count | Per week |
|---|---|---|
| (close-to-close ≥3σ) | 30 | 0.6 |
| digest:2σ move (intraday touch) | 255 | 5.1 |
| digest:goal restart | 2 | 0.0 |
| digest:new recommendation | 47 | 0.9 |
| urgent:3σ move (intraday touch) | 67 | 1.3 |
| urgent:goal missed, short-term paused | 3 | 0.1 |
| urgent:stop | 13 | 0.3 |
| urgent:target | 9 | 0.2 |

## Watchlist alert rates (if every symbol were held)

61 symbols over 252 sessions.

| Measure | Total | Per symbol per month |
|---|---|---|
| 2σ–3σ close-to-close move | 753 | 1.03 |
| ≥3σ close-to-close move | 235 | 0.32 |
| 2σ–3σ intraday touch | 1430 | 1.95 |
| ≥3σ intraday touch | 470 | 0.64 |
