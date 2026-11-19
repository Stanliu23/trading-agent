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

## Long-term share cut to 15–20% (2026-11-18)

$1,800 deposited on the same days ($300 on 2026-05-18, then $250 on the first session of each month), value on 2026-11-18:

| Where the money went | Value | vs $1,800 |
|---|---|---|
| T-bills only (BIL) | $1,819.76 | +$19.76 |
| **This agent** (15–20% long-term, goal safeguard on) | **$1,792.61** | −$7.39 |
| VTI/QQQ/SCHD only, equal | $1,769.69 | −$30.31 |
| SPY only | $1,749.68 | −$50.32 |

- In this window, nothing invested in stocks ended above the money put in. Only T-bills did.
- The agent beat the index funds mainly because the goal safeguard paused short-term trading on 2026-08-21, leaving 83% of the account in cash at the end, while stocks dipped. That came from sitting out, not from skill.
- Time-weighted +1.1% vs SPY −0.6%. Short-term: 17 trades, −$5.96 (S3 7 of 7 winners, +$25.42; S2 3 of 9, −$22.48).

## Aggressive vs moderate, and 17.5% vs 0% long-term (2026-11-18)

Same rules otherwise ($300 start + $250 per month, goal safeguard on, every recommendation taken). Idle cash earns 0% in the simulator.

**24 months (2024-11-18 to 2026-11-18), $6,300 deposited:**

| Variant | End value | Short-term P&L | Goal pause |
|---|---|---|---|
| Aggressive under $1k, 17.5% long-term (current) | $6,489.87 | +$0.06 (30 trades) | 2025-05-16 |
| Aggressive under $1k, 0% long-term | $6,303.49 | +$3.49 (34) | 2025-05-16 |
| Moderate from start, 17.5% long-term | $6,487.72 | +$3.10 (20) | 2025-02-21 |
| Moderate from start, 0% long-term | $6,306.16 | +$6.16 (20) | 2025-02-21 |
| Index funds only (VTI/QQQ/SCHD) | $7,338.83 | – | – |
| SPY only | $7,112.22 | – | – |
| T-bills only (BIL) | $6,554.88 | – | – |

**6 months (2026-05-18 to 2026-11-18), $1,800 deposited:** aggressive $1,792.61; moderate from start $1,805.63; with 0% long-term $1,797.97 and $1,801.69; index funds only $1,769.69; T-bills $1,819.76.

Findings:
- **Aggressive vs moderate makes almost no difference** (−$13 to +$2). At $250 a month, deposits pass $1,000 within about 3 months, so the aggressive phase is short.
- **Long-term funds produced nearly all of the 24-month gain** (+$184 vs ≈$0 with 0% long-term). Short-term trading netted about $0 over 2 years.
- **Biggest problem:** the goal safeguard paused short-term trading early (Feb or May 2025) and never restarted, because the replay has no restart rule. So about 82% of each deposit sat in cash earning nothing for most of 2 years. That is why the agent trails index-only by about $850 and even trails T-bills.
