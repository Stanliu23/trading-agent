# Hidden problems found by the 6-month replay (2026-11-18)

Hypothetical account: $300 to start, $250 on the first session of each month, from 2026-05-18 to 2026-11-18, with every recommendation taken. See `docs/REPLAY.md` for the numbers.

## Fixed in code

1. **Bucket-drift alert repeated daily.** 84 alerts in 6 months. It now fires once per episode, and once rather than twice (the two buckets always add up to 100%).
2. **Sizes rounded up could overspend cash** by up to half a cent. Sizes now round down to the cent.
3. **"No room" hid its reason.** Sizing now always names the limit that bound it (cash, bucket room, position cap or risk).
4. **The report overstated drops and hid performance.** Deposits soften the raw account value, so the report now shows a time-weighted return against SPY. The weekly email must use the same measure.

## Needs your decision

5. **Ties are broken alphabetically.** Every signal from one setup has the same expected return, so ranking falls back to the ticker's letter: 70% of short-term trades went to A–M tickers.
6. **Positions too small to matter.** 12 positions under $20 (smallest $1.17), made from leftover cash.
7. **L1 has no rule for which ETF to buy.** The replay spread purchases across SPY, QQQ, VTI and SCHD. SPY and VTI are near-duplicates.
8. **S1 carries most trades but has the least edge.** 77 of 97 trades, roughly break-even (+0.04% average), Edge 1 of 5.

## For your information

9. **Underperformance.** Time-weighted −6.5% vs SPY −0.6% over 6 months, and short-term trades lost $128.83. Six months is a small sample, but the 2-week shadow run should watch this.
10. **The aggressive phase lasts about 3 months.** With $250/month, deposits alone pass $1,000 by the 4th month (switched 2026-08-03 in the replay).
11. **Half of the urgent move alerts fade by the close.** 20 intraday 3σ touches vs 10 closes beyond 3σ.
12. **News volume.** About 18 Yahoo headlines per symbol per week, and the RSS feed holds only the latest 20. With about 10 holdings that's about 180 headlines a week, so Phase 6 needs a cheap filter before the AI reads them.
13. **Fit (the third star score) has no formula yet.** It's needed before emails can show stars.
14. **SEC filing alerts are off** until a contact email is chosen (the SEC requires one).
15. **The long-term bucket ended at 27%,** below the moderate band (30–40%), after the profile switch. Deposit splits close the gap slowly.
