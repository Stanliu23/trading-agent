# Strategy tournament results

Today's rules, short-term sleeve: design +28.9%, check +74.1%, 2026 +7.2% ($1,000, no deposits).

Model check: rebuilt 40/60 account vs the real simulator, median gain 12.6% vs 12.4%, median worst drop -13.1% vs -13.2%.

## Pass bar at 40/60

| strategy | design % | check % | step 1 | better in | median gain pts | median drop pts | step 2 | 2026 % | step 3 | PASS |
|---|---|---|---|---|---|---|---|---|---|---|
| Donchian breakout | 34.7 | 9.4 | True | 39% | -2.0 | 1.3 | False | 5.5 | True | False |
| Low volatility | 130.3 | 19.3 | True | 58% | 1.8 | -1.3 | False | 22.0 | True | False |
| Stock momentum | 463.9 | 59.3 | True | 83% | 5.1 | -8.0 | False | 37.6 | True | False |
| Short-term reversal | 738.0 | 68.8 | True | 83% | 11.3 | -7.8 | False | 1.6 | True | False |
| S3 with market filter | 33.7 | 68.6 | True | 47% | 0.0 | 0.0 | False | 7.0 | True | False |
| Sector rotation | 184.4 | 20.0 | True | 61% | 2.2 | -3.9 | False | -6.0 | False | False |
| ETF trend timing | 61.9 | 27.3 | True | 42% | -0.6 | 0.3 | False | 2.4 | True | False |

**Picks (pick rule):** none passed

## Long/short splits (36 starts, $300 + $250/month, 24 months)

Median gain on money deposited / median worst drop / share of starts better than today's 40/60.

| strategy | 100/0 | 80/20 | 60/40 | 40/60 | 20/80 | 0/100 |
|---|---|---|---|---|---|---|
| Today's rules | +17.8% / -19.6% / 58% | +14.8% / -17.8% / 58% | +13.1% / -15.8% / 58% | +12.6% / -13.1% / 0% | +9.5% / -12.1% / 42% | +6.6% / -12.1% / 42% |
| Donchian breakout | +17.8% / -19.6% / 58% | +15.1% / -16.6% / 56% | +12.5% / -13.5% / 44% | +9.7% / -11.0% / 39% | +7.0% / -8.7% / 31% | +4.5% / -8.4% / 17% |
| Low volatility | +17.8% / -19.6% / 58% | +16.1% / -17.3% / 64% | +15.3% / -15.0% / 67% | +14.0% / -12.8% / 58% | +11.9% / -11.9% / 56% | +10.9% / -12.4% / 50% |
| Stock momentum | +17.8% / -19.6% / 58% | +20.7% / -21.5% / 67% | +21.9% / -22.0% / 67% | +23.3% / -22.3% / 83% | +23.9% / -22.2% / 81% | +23.2% / -22.2% / 81% |
| Short-term reversal | +17.8% / -19.6% / 58% | +21.0% / -20.5% / 72% | +22.7% / -21.4% / 83% | +22.5% / -21.3% / 83% | +24.5% / -21.6% / 89% | +26.0% / -22.4% / 89% |
| S3 with market filter | +17.8% / -19.6% / 58% | +15.5% / -16.6% / 67% | +14.6% / -13.9% / 64% | +13.0% / -12.1% / 47% | +10.6% / -9.9% / 53% | +8.5% / -9.9% / 50% |
| Sector rotation | +17.8% / -19.6% / 58% | +17.1% / -18.6% / 56% | +16.7% / -17.9% / 58% | +15.4% / -16.4% / 61% | +14.0% / -15.0% / 64% | +13.3% / -14.3% / 53% |
| ETF trend timing | +17.8% / -19.6% / 58% | +16.3% / -17.6% / 58% | +14.8% / -15.5% / 47% | +13.1% / -13.4% / 42% | +11.2% / -11.3% / 36% | +8.4% / -9.5% / 33% |

## Market conditions (short-term sleeve alone, Jan 2015 - Nov 2026)

Annualised return on the days in each condition:

| strategy | Calm (VIX normal) | SPY above 200-day | SPY below 200-day | Stress (VIX top 20%) |
|---|---|---|---|---|
| Donchian breakout | 3.8 | 4.6 | -1.7 | 2.6 |
| Index funds only (L1) | 10.5 | 11.2 | 17.1 | 19.0 |
| Low volatility | 10.7 | 10.3 | 12.8 | 10.8 |
| Stock momentum | 13.8 | 21.0 | 38.5 | 74.5 |
| Short-term reversal | 19.3 | 16.8 | 75.9 | 52.5 |
| S3 with market filter | 8.5 | 7.7 | -0.5 | -2.6 |
| Sector rotation | 7.9 | 8.9 | 18.0 | 21.1 |
| SPY | 10.9 | 11.5 | 17.8 | 19.7 |
| Today's rules | 6.1 | 6.1 | -4.2 | -3.1 |
| ETF trend timing | 6.2 | 7.5 | 1.8 | 7.9 |

Return in each episode (%):

| strategy | 2018 Q4 sell-off | 2020 crash | 2020 rebound | 2022 bear market | 2023 recovery | 2025 tariff sell-off |
|---|---|---|---|---|---|---|
| Donchian breakout | -4.1 | -4.7 | 12.1 | -8.3 | 13.0 | -4.2 |
| Index funds only (L1) | -20.0 | -35.0 | 59.9 | -25.4 | 35.1 | -19.3 |
| Low volatility | -7.8 | -25.1 | 38.2 | -9.1 | 12.1 | -7.4 |
| Stock momentum | -27.7 | -32.5 | 71.4 | -9.7 | 40.0 | -25.9 |
| Short-term reversal | -21.9 | -40.5 | 135.5 | -12.6 | 52.8 | -17.2 |
| S3 with market filter | -4.3 | -13.7 | -0.0 | -8.0 | 5.8 | -9.5 |
| Sector rotation | -14.6 | -31.5 | 64.2 | -8.7 | 19.7 | -17.7 |
| SPY | -19.3 | -33.7 | 57.4 | -24.5 | 36.0 | -18.8 |
| Today's rules | -9.9 | 0.3 | -0.0 | -7.9 | 5.8 | -9.5 |
| ETF trend timing | -9.1 | -10.2 | 11.0 | -7.3 | 3.9 | -7.6 |

Worst drop in each episode (%):

| strategy | 2018 Q4 sell-off | 2020 crash | 2020 rebound | 2022 bear market | 2023 recovery | 2025 tariff sell-off |
|---|---|---|---|---|---|---|
| Donchian breakout | -4.0 | -5.1 | -8.5 | -8.9 | -5.9 | -4.0 |
| Index funds only (L1) | -20.0 | -34.8 | -7.5 | -25.2 | -10.7 | -18.9 |
| Low volatility | -11.3 | -25.2 | -6.0 | -15.1 | -11.0 | -9.6 |
| Stock momentum | -29.3 | -33.0 | -9.3 | -17.1 | -13.3 | -24.2 |
| Short-term reversal | -25.6 | -41.8 | -7.6 | -22.6 | -12.7 | -18.4 |
| S3 with market filter | -7.8 | -13.3 | -0.1 | -8.7 | -0.0 | -8.7 |
| Sector rotation | -15.3 | -31.2 | -5.9 | -14.4 | -12.9 | -16.8 |
| SPY | -19.3 | -33.4 | -7.0 | -24.5 | -10.0 | -18.4 |
| Today's rules | -10.9 | -0.0 | -0.1 | -8.7 | -0.0 | -8.4 |
| ETF trend timing | -9.1 | -10.7 | -2.0 | -9.0 | -6.4 | -7.4 |
