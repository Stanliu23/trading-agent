# Hidden problems found by the 6-month replay (2026-11-18)

Hypothetical account: $300 to start, $250 on the first session of each month, from 2026-05-18 to 2026-11-18, with every recommendation taken. See `docs/REPLAY.md` for the numbers.

## Fixed in code

1. **Bucket-drift alert repeated daily.** 84 alerts in 6 months. It now fires once per episode, and once rather than twice (the two buckets always add up to 100%).
2. **Sizes rounded up could overspend cash** by up to half a cent. Sizes now round down to the cent.
3. **"No room" hid its reason.** Sizing now always names the limit that bound it (cash, bucket room, position cap or risk).
4. **The report overstated drops and hid performance.** Deposits soften the raw account value, so the report now shows a time-weighted return against SPY. The weekly email must use the same measure.

## Decided and fixed (2026-11-18)

5. ~~Ties are broken alphabetically.~~ **Fixed:** ties go to the idea least correlated with your holdings, which is also the Fit score. Every signal from one setup has the same expected return, so ranking falls back to the ticker's letter: 70% of short-term trades went to A–M tickers.
6. ~~Positions too small to matter.~~ **Fixed:** $20 minimum. 12 positions under $20 (smallest $1.17), made from leftover cash.
7. ~~L1 has no rule for which ETF to buy.~~ **Fixed:** VTI, QQQ, SCHD, buying whichever is held least. Re-running also exposed a bug: "held least" counted only the latest lot, so QQQ got 4 of 6 buys. Now every lot is summed. The replay spread purchases across SPY, QQQ, VTI and SCHD. SPY and VTI are near-duplicates.
8. ~~S1 carries most trades but has the least edge.~~ **Fixed:** setups need Edge ≥ 2, which removes S1. 77 of 97 trades, roughly break-even (+0.04% average), Edge 1 of 5.

## For your information

9. **Underperformance.** Time-weighted −6.5% vs SPY −0.6% over 6 months, and short-term trades lost $128.83. Six months is a small sample, but the 2-week shadow run should watch this.
10. **The aggressive phase lasts about 3 months.** With $250/month, deposits alone pass $1,000 by the 4th month (switched 2026-08-03 in the replay).
11. **Half of the urgent move alerts fade by the close.** 20 intraday 3σ touches vs 10 closes beyond 3σ.
12. **News volume.** About 18 Yahoo headlines per symbol per week, and the RSS feed holds only the latest 20. With about 10 holdings that's about 180 headlines a week, so Phase 6 needs a cheap filter before the AI reads them.
13. ~~Fit has no formula yet.~~ **Fixed:** correlation steps, see SPEC §4. It's needed before emails can show stars.
14. **SEC filing alerts are off** until a contact email is chosen (the SEC requires one).
15. **The long-term bucket ended at 27%,** below the moderate band (30–40%), after the profile switch. Deposit splits close the gap slowly.

## After the fixes (rerun 2026-11-18)

- Time-weighted −7.9% vs SPY −0.6% (before the fixes: −6.5%). Short-term trades: 31 (was 97), 35% winners, −$145.08.
- **New issue: idle cash.** Without S1 there are few signals, so cash sat idle at 31% of the account on average (was 19%).
- In this window S2 won 3 of 12 trades (backtest: 50% winners) and S3 won 8 of 17 (backtest: 71%). Results that bad happen about 1 time in 20 by chance for each setup. That's a small sample, but the shadow run should watch it.
- L1's statistics changed with SPY removed: 567 windows, 8% losing, 5th percentile −13.8%, now **Tier 2** (was 3), Edge 4, Confidence 2.

## Goal safeguard (added 2026-11-18)

Rule: short-term trading must beat holding VTI/QQQ/SCHD over 3 months, or it pauses until you approve a restart.

- In the replay it paused on 2026-08-21: short-term +1.0% vs index funds +4.7% over 63 sessions.
- 6-month result: time-weighted −0.0% (was −7.9%), vs SPY −0.6%. Short-term P&L −$15.41 over 16 trades (was −$145.08 over 31).
- **Trade-off:** while paused, short-term cash sits idle (50% of the account on average, 66% at the end), because money never moves to the long-term bucket.
- **Open question:** what evidence should a restart need? A natural option is to keep tracking the paused setups on paper, so the weekly report shows whether they would have worked.
