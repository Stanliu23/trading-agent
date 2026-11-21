# Setup statistics

Approved by Stanley on 2026-11-18. Any change to a setup rule or a scoring step needs a new backtest and a new approval.

Generated 2026-11-20 by `uv run tradeagent backtest-setups`.
Data: Yahoo daily bars, adjusted for splits and dividends, from 2015-01-01 to 2025-12-31, fetched through Vibe-Trading's loader.
Long-term setups use 2005-01-01 to 2025-12-31 and are scored on 3-year forward returns.
Costs: 0.1% per round trip. Held-out period: short-term trades entered from 2024-01-01 on; long-term, the last 2 years of complete entries.

| Setup | Trades | Loss rate | Avg | Median | 5th pct | Worst | Exp. R | Held-out | Years + | Evidence | Tier | Edge | Conf. | Used? |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **S1** Trend pullback | 4872 | 36% | +0.19% | +0.57% | -5.3% | -26.8% | +0.03 | +0.05R (1031) | 82% | pass | 2 | 1 | 5 | no (Edge < 2) |
| **S2** 52-week-high breakout | 1389 | 53% | +0.52% | -1.21% | -6.4% | -19.0% | +0.10 | +0.16R (273) | 80% | pass | 3 | 3 | 5 | yes |
| **S3** ETF dip in uptrend | 628 | 29% | +0.77% | +1.37% | -5.1% | -11.8% | +0.19 | +0.17R (129) | 91% | pass | 2 | 3 | 5 | yes |
| **S4** Big gap-up continuation | 174 | 50% | +0.87% | +0.24% | -6.5% | -9.4% | +0.29 | +0.16R (33) | 64% | pass | 3 | 3 | 3 | yes |
| **L1** Core index accumulation | 567 | 8% | +44.60% | +43.79% | -13.8% | -42.1% | – | +38.0% (75) | 89% | pass | 2 | 4 | 2 | yes |

## Column meanings

- **Loss rate:** share of trades that lost money after costs. Tier 1 needs ≤ 25%, Tier 2 ≤ 40%.
- **5th pct:** 1 in 20 trades did worse than this. Tier 1 needs ≥ −8%, Tier 2 ≥ −15%.
- **Worst:** the single worst trade, usually an earnings gap through the stop. Shown for information; it doesn't set the tier.
- **Exp. R:** average result per unit of risk (1R = the distance from entry to stop).
- **Held-out:** the same metric on trades entered after the cutoff, which the setups were never shaped on.
- **Years +:** share of calendar years whose average trade was positive.
- **Edge / Conf.:** two of the three star sub-scores. **Fit** is added per recommendation: 5 minus the correlation steps (0.2, 0.4, 0.6, 0.8, 0.9) that the idea's 60-day correlation with your holdings exceeds.
- **Used?:** a setup is recommended only if it passes the evidence rules and scores at least 2 on Edge.

## Setup rules

- **S1 Trend pullback** (short-term, 60 symbols): Price above its 200-day average and 2-day RSI below 10. Exit when the close is back above the 5-day average, at a 2.5×ATR stop, or after 10 days.
- **S2 52-week-high breakout** (short-term, 77 symbols): Close at a 52-week high on volume 1.5× its 50-day average, above the 200-day average. Stop 2×ATR, target 4×ATR, exit after 20 days.
- **S3 ETF dip in uptrend** (short-term, 20 symbols): ETF closes below its lower Bollinger band (20, 2) while above its 200-day average. Exit when the close is back above the 20-day average, at a 3×ATR stop, or after 15 days.
- **S4 Big gap-up continuation** (short-term, 77 symbols): Opens ≥4% above the prior close on 3× average volume and closes in the top half of its range (usually earnings). Stop at that day's low, target 2× the risk, exit after 20 days.
  - Note: Proxy for post-earnings drift: no historical earnings dates in the free data.
- **L1 Core index accumulation** (long-term, 3 symbols): Buy broad index ETFs (VTI, QQQ, SCHD) with each deposit, into whichever is held least. Sell only on a measured thesis break, never on price noise.
  - Note: Scored on 3-year forward returns from every month start; windows overlap, so Confidence is capped at 2.

## Known limits

- **Survivorship bias:** the stock list is today's large caps, so S2 and S4 (and S1's stock half) look better than they would have in real time.
- Trades on different stocks that open on the same day are correlated, so the real sample is smaller than the trade count.
- Daily bars can't show which of stop and target was hit first in a day. The simulator always assumes the stop.
- Live, the agent skips short-term stock entries when earnings fall before the planned exit. The free data has no historical earnings dates, so these stats still include trades held through earnings.
- Long-term windows overlap (one starts every month), so their trade count overstates the independent evidence.
