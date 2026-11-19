# Setup statistics

Approved by Stanley on 2026-11-18. Any change to a setup rule or a scoring step needs a new backtest and a new approval.

Generated 2026-11-18 by `uv run tradeagent backtest-setups`.
Data: Yahoo daily bars, adjusted for splits and dividends, from 2015-01-01 to 2025-12-31, fetched through Vibe-Trading's loader.
Long-term setups use 2005-01-01 to 2025-12-31 and are scored on 3-year forward returns.
Costs: 0.1% per round trip. Held-out period: short-term trades entered from 2024-01-01 on; long-term, the last 2 years of complete entries.

| Setup | Trades | Loss rate | Avg | Median | 5th pct | Worst | Exp. R | Held-out | Years + | Evidence | Tier | Edge | Conf. |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **S1** Trend pullback | 4872 | 36% | +0.19% | +0.57% | -5.3% | -26.8% | +0.03 | +0.05R (1031) | 82% | pass | 2 | 1 | 5 |
| **S2** 52-week-high breakout | 741 | 50% | +0.98% | -0.26% | -6.3% | -19.0% | +0.17 | +0.24R (127) | 90% | pass | 3 | 4 | 5 |
| **S3** ETF dip in uptrend | 628 | 29% | +0.77% | +1.37% | -5.1% | -11.8% | +0.19 | +0.17R (129) | 91% | pass | 2 | 3 | 5 |
| **S4** Big gap-up continuation | 90 | 44% | +1.41% | +1.61% | -7.1% | -9.4% | +0.47 | +0.42R (19) | 64% | pass | 3 | 5 | 2 |
| **L1** Core index accumulation | 783 | 10% | +42.25% | +41.70% | -17.3% | -42.1% | – | +39.4% (100) | 89% | pass | 3 | 4 | 2 |

## Column meanings

- **Loss rate:** share of trades that lost money after costs. Tier 1 needs ≤ 25%, Tier 2 ≤ 40%.
- **5th pct:** 1 in 20 trades did worse than this. Tier 1 needs ≥ −8%, Tier 2 ≥ −15%.
- **Worst:** the single worst trade, usually an earnings gap through the stop. Shown for information; it doesn't set the tier.
- **Exp. R:** average result per unit of risk (1R = the distance from entry to stop).
- **Held-out:** the same metric on trades entered after the cutoff, which the setups were never shaped on.
- **Years +:** share of calendar years whose average trade was positive.
- **Edge / Conf.:** two of the three star sub-scores. **Fit** is added per recommendation, from your current holdings.

## Setup rules

- **S1 Trend pullback** (short-term, 60 symbols): Price above its 200-day average and 2-day RSI below 10. Exit when the close is back above the 5-day average, at a 2.5×ATR stop, or after 10 days.
- **S2 52-week-high breakout** (short-term, 40 symbols): Close at a 52-week high on volume 1.5× its 50-day average, above the 200-day average. Stop 2×ATR, target 4×ATR, exit after 20 days.
- **S3 ETF dip in uptrend** (short-term, 20 symbols): ETF closes below its lower Bollinger band (20, 2) while above its 200-day average. Exit when the close is back above the 20-day average, at a 3×ATR stop, or after 15 days.
- **S4 Big gap-up continuation** (short-term, 40 symbols): Opens ≥4% above the prior close on 3× average volume and closes in the top half of its range (usually earnings). Stop at that day's low, target 2× the risk, exit after 20 days.
  - Note: Proxy for post-earnings drift: no historical earnings dates in the free data.
- **L1 Core index accumulation** (long-term, 4 symbols): Buy broad index ETFs (SPY, QQQ, VTI, SCHD) with each deposit. Sell only on a measured thesis break, never on price noise.
  - Note: Scored on 3-year forward returns from every month start; windows overlap, so Confidence is capped at 2.

## Known limits

- **Survivorship bias:** the stock list is today's large caps, so S2 and S4 (and S1's stock half) look better than they would have in real time.
- Trades on different stocks that open on the same day are correlated, so the real sample is smaller than the trade count.
- Daily bars can't show which of stop and target was hit first in a day. The simulator always assumes the stop.
- Live, the agent skips short-term stock entries when earnings fall before the planned exit. The free data has no historical earnings dates, so these stats still include trades held through earnings.
- Long-term windows overlap (one starts every month), so their trade count overstates the independent evidence.
