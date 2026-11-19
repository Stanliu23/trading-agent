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

## Fixes for idle cash, and the 40/60 split (2026-11-18)

Switches added to the simulator, all off by default: T-bill interest on idle cash; deposits to long-term while paused; restart once the paper book (the same account run without the pause) is no longer behind the index funds over 63 sessions. After a restart, the next pause check waits a full 63 sessions.

**24 months, $6,300 deposited** (index funds only: +$1,038.83; T-bills only: +$254.88):

| Version | vs deposits | Worst drop | Short-term P&L | Pauses/restarts |
|---|---|---|---|---|
| Old: 17.5% long-term, aggressive start | +$189.87 | −8.7% | +$0.06 | 1/0 |
| Old + T-bills on idle cash | +$398.77 | −8.5% | +$0.17 | 1/0 |
| Old + deposits to long-term while paused | +$594.55 | −8.7% | +$0.06 | 1/0 |
| Old + restart rule | +$634.31 | −8.7% | +$445.51 | 5/4 |
| Old + restart + T-bills | +$756.65 | −8.5% | +$449.27 | 5/4 |
| Old, no safeguard | +$509.28 | −11.0% | +$308.61 | 0/0 |
| **New: 40/60, moderate from start** | **+$416.88** | −11.3% | +$10.32 | 1/0 |
| New + T-bills | +$576.80 | −11.2% | +$10.39 | 1/0 |
| New + restart rule | +$646.73 | −11.3% | +$219.22 | 6/5 |
| New + restart + T-bills | +$474.53 | −11.2% | −$55.91 | 5/4 |
| New, no safeguard | +$623.03 | −11.3% | +$167.96 | 0/0 |

**6 months, $1,800 deposited** (index funds only: −$30.31; T-bills only: +$19.76): old −$7.39; new 40/60 −$12.68; new + T-bills −$3.38; the restart rule didn't fire. Without the safeguard: old −$131.44, new −$101.35.

What this shows:
- **40/60 vs 17.5/82.5:** better over 24 months (+$417 vs +$190), slightly worse over the flat 6 months (−$12.68 vs −$7.39), with a deeper worst drop (−11.3% vs −8.7%). More money in index funds helped while the market rose.
- **Restart rule:** the most consistent help over 24 months. Over the 6 months it never fired (the paper book stayed behind), which is the point of it.
- **Results are path-dependent:** adding T-bills to new + restart *lowered* the result by $172, because a slightly different cash balance changed which trades happened and when the restart fired. Differences of a few hundred dollars between versions are partly luck.
- **Nothing beat holding the index funds over 24 months.** The short-term part is still the drag.

## Long/short splits compared, restart rule adopted (2026-11-18)

Moderate rules from the start, $300 + $250 per month, every recommendation taken. Split = long-term/short-term with a ±5-point band. "Restart" = restart rule on (the simulator assumes you approve each restart).

| Split | 60 months ($15,300 in) | 24 months ($6,300 in) | 6 months ($1,800 in) | Worst drop (60 mo) |
|---|---|---|---|---|
| 100/0 | +$5,563 | +$781 | −$29 | −19.5% |
| 20/80 | +$1,260 | +$215 | +$3 | −8.5% |
| 20/80 + restart | +$4,286 | +$390 | +$3 | −10.2% |
| 40/60 | +$2,639 | +$417 | −$13 | −12.7% |
| **40/60 + restart (current)** | **+$5,888** | **+$647** | **−$13** | −14.4% |
| 60/40 | +$4,108 | +$677 | −$46 | −18.5% |
| 60/40 + restart | +$9,194 | +$1,097 | −$46 | −20.0% |
| *Index funds only (no position cap)* | *+$7,516* | *+$1,039* | *−$30* | – |
| *SPY only* | *+$7,303* | *+$812* | *−$50* | – |
| *T-bills only* | *+$1,722* | *+$255* | *+$20* | – |

What this shows:
- **More long-term = more gain in rising periods and deeper drops.** The ranking flips over the flat last 6 months, where 20/80 did best.
- **The restart rule helps every split over 60 and 24 months.** In 60 months it paused and restarted 10–13 times, so expect several pause/restart emails a year.
- **60/40 + restart is the only version that beat index funds only** (60 months +$9,194 vs +$7,516; 24 months +$1,097 vs +$1,039). It also had the deepest drop (−20%).
- **Hidden problem: 100/0 can't actually reach 100%.** The 25% per-position cap with only 3 long-term ETFs limits long-term holdings to 75%, so about 25% sat idle. That is why 100/0 trails "index funds only".
- **Caveat on the 60-month window:** it overlaps 2021–2023, which the setups were designed on, so it flatters short-term trading. The 6-month window (2026) is the only fully unseen period, and there no version beat T-bills.

## Restart + T-bills, and are the safeguards needed? (2026-11-18)

Profit vs deposits. "Restart" = goal safeguard on with the restart rule. "Off" = goal safeguard off, T-bills on.

| Split | Version | 60 mo ($15,300) | 24 mo ($6,300) | 12 mo ($3,300) | 6 mo ($1,800) |
|---|---|---|---|---|---|
| 20/80 | restart | +$4,286 | +$390 | −$93 | +$3 |
| 20/80 | restart + T-bills | +$4,864 | +$751 | −$59 | +$7 |
| 20/80 | safeguard off | +$7,431 | +$577 | −$23 | −$114 |
| 40/60 | restart | +$5,888 | +$647 | −$26 | −$13 |
| 40/60 | restart + T-bills | +$5,780 | +$475 | −$2 | −$3 |
| 40/60 | safeguard off | +$7,359 | +$682 | +$3 | −$98 |
| 60/40 | restart | +$9,194 | +$1,097 | −$71 | −$46 |
| 60/40 | restart + T-bills | +$10,003 | +$1,166 | −$57 | −$40 |
| 60/40 | safeguard off | +$8,661 | +$644 | −$22 | −$103 |
| – | *index funds only* | *+$7,516* | *+$1,039* | *+$194* | *−$30* |
| – | *T-bills only* | *+$1,722* | *+$255* | *+$67* | *+$20* |

What this shows:
- **T-bills on idle cash helped in 10 of 12 split/window cases** (the exceptions: 40/60 over 60 and 24 months, a path effect).
- **The goal safeguard is insurance, not a profit engine.** In 2026 (the only fully unseen period) it saved about $100 per $1,800 in every split. Over longer windows it sometimes cost money (20/80 and 40/60 over 60 months) and sometimes added (60/40 over 24 and 60 months).
- **Over the last 12 months, short-term trading lost money in every version** (−$89 to −$203), and every version trailed both index funds (+$194) and T-bills (+$67).
- **Hidden problem: the drawdown pause never fired,** in any version or window, even with a −20% time-weighted drop. It measures the drop on raw account value, and monthly deposits hide the fall. It should measure the drop with deposits removed (time-weighted).
- Turning the drawdown pause off changed nothing, for the same reason.

## Why short-term trading loses money lately (2026-11-18)

**Each setup's paper record, every signal on the watchlist, no portfolio limits:**

| Setup | Design 2015–23 | Check 2024–25 | Unseen 2026 |
|---|---|---|---|
| S2 breakouts | 49% wins, +0.15R | 54%, +0.25R | 44%, **+0.21R** (still works) |
| S3 ETF dips | 71% wins, +0.19R | 71%, +0.17R | **54%, −0.08R** (broke) |
| S4 gap-ups | 57%, +0.46R | 47%, +0.42R | 29%, −0.27R (7 trades only) |

**Dollars in the account (40/60, no pause):** S2 +$14 (12 months) and +$406 (24 months); **S3 −$106 and −$111**; S4 −$15 and −$128.

What this shows:
- **The losses come from S3, not from short-term trading in general.** S3's ETFs move little, so its positions are sized up to the 25% cap, and its losers are large in dollars (12 months: losers averaged $352, winners $241).
- **Picking isn't the problem.** The account's S2 trades averaged +1.13% vs +1.39% for all S2 signals, with the same sector mix. (My earlier guess that the correlation tiebreak picks weak sectors was wrong.)
- **The market-trend filter wouldn't help in 2026.** SPY was above its 200-day average on 95% of days. Dips simply stopped bouncing back as reliably.
- **Recent months were rough for every setup:** August–November 2026 entries won 0–40% of the time.
- **The goal safeguard pauses everything, including S2, which still works.**

**Fix tested: a per-setup switch.** A setup is skipped while its last 20 paper trades average below 0R, and resumes when they turn positive. The numbers were set before testing.

| 40/60 | 60 mo | 24 mo | 12 mo | 6 mo |
|---|---|---|---|---|
| Current (goal pause + restart + T-bills) | +$5,780 | +$475 | −$2 | −$3 |
| Switch + goal pause + restart | +$6,730 | +$556 | +$52 | −$24 |
| Switch only | +$6,841 | +$599 | +$81 | −$50 |
| No safeguards | +$7,359 | +$682 | +$3 | −$98 |

The switch plus the goal pause beats current in 3 of 4 windows, and gives up $21 in the last 6 months. It reacts after a setup's damage starts (20 trades), so S3 still lost $73–84.

## Best long/short ratio (2026-11-18)

All current rules plus the per-setup switch. Profit as % of money deposited:

| Long/short | 60 mo | 24 mo | 12 mo | 6 mo | Worst drop (60 mo) | Worst-case gap to the best split |
|---|---|---|---|---|---|---|
| 0/100 | +23.4% | +5.3% | −1.8% | −0.7% | −8.2% | 23.6 pts |
| 20/80 | +22.3% | +5.6% | −0.8% | −1.0% | −8.0% | 24.7 pts |
| 30/70 | +30.0% | +6.3% | −2.6% | −1.3% | −9.2% | 17.0 pts |
| 40/60 (current) | +44.0% | +8.8% | +1.6% | −1.3% | −11.2% | 7.1 pts |
| 50/50 | +42.9% | +7.5% | +3.5% | −2.0% | −12.6% | 8.4 pts |
| **60/40** | **+47.0%** | +15.0% | +3.1% | −1.9% | −14.7% | **2.0 pts** |
| 70/30 | +41.2% | **+15.9%** | **+5.1%** | −1.2% | −16.8% | 5.8 pts |
| 75/25 (max possible) | +43.7% | +14.0% | +4.8% | −1.9% | −18.8% | 3.4 pts |

- **No single split wins every window.** 60/40 is the most robust: it never trails the best split by more than 2 points, and it has the best long-window result. 70/30 ranks best on average across the recent windows, but trails by 5.8 points over 60 months.
- **More long-term = deeper drops** (−8% at 0/100 up to −19% at 75/25).
- **Above 75% long-term is impossible** under the 25% position cap with 3 long-term ETFs.
- **Caveat:** these windows mostly had rising markets, which favour more long-term. Choosing a ratio from them is itself fitting to the past.
- **The per-setup switch's effect depends on the split:** it helped 40/60 in 3 of 4 windows, but cost 60/40 about 18 points over 60 months. Treat it as insurance, not a sure gain.

## How far trades move before exiting (design years 2015–23 only)

| | S2 breakouts | S3 ETF dips | S4 gap-ups |
|---|---|---|---|
| Losers that were up ≥ +0.5R first | 43% | 18% | 50% |
| Losers that were up ≥ +1R first | 12% | 0% | 17% |
| Winners: best point → close (median) | +1.92R → +1.53R | +0.80R → +0.60R | +2.11R → +1.96R |
| Trades reaching +3R | 2% | 0% | 3% |
| Winners that first dipped below −0.5R | 33% | 25% | 37% |

Ideas to test (not adopted; each would need design → check → unseen-2026):
- **S2:** move the stop to breakeven after +1R, which would affect the 12% of losers that were up +1R first. A bigger target is pointless, since only 2% of trades reach +3R.
- **S3:** moves are small (winners peak at +0.8R), so its 3×ATR stop is wide relative to the gain. Test a 2×ATR stop and a shorter time limit.
- **S4:** exits already capture most of the move; leave as is.

## Exit changes tested (2026-11-18): none adopted

Decision rule, fixed before looking at results: keep a change only if it raises the average result per trade in the design years (2015–23), AND is not worse in the check years (2024–25), AND is not worse in unseen 2026.

**Per trade, every watchlist signal (average R; win rate):**

| Variant | Design 2015–23 | Check 2024–25 | Unseen 2026 | Verdict |
|---|---|---|---|---|
| S2 current | +0.152R, 49% | +0.247R, 54% | +0.213R, 44% | – |
| S2 + breakeven after +1R | +0.127R, 42% | +0.148R, 43% | +0.118R, 33% | rejected: worse in all 3 |
| S3 current | +0.193R, 71% | +0.174R, 71% | −0.078R, 54% | – |
| S3 10-day limit | +0.167R | +0.198R | −0.040R | rejected: worse in design |
| S3 2×ATR stop | +0.228R | +0.303R | −0.093R | borderline: see account test |
| S3 2×ATR + 10-day | +0.208R | +0.312R | −0.086R | borderline: see account test |

S3 positions usually hit the 25% size cap, so dollars follow % per trade more than R. By % per trade, the 2×ATR stop was worse in design (0.62% vs 0.75%), better in check (0.95% vs 0.82%) and better in 2026 (−0.24% vs −0.31%). So I ran the account test.

**Simulated account (40/60, current rules), profit vs deposits:**

| S3 variant | 60 mo | 24 mo | 12 mo | 6 mo |
|---|---|---|---|---|
| Current (3×ATR, 15 days) | +$6,730 | +$556 | +$52 | −$24 |
| 2×ATR stop | +$5,639 | +$499 | +$144 | −$22 |
| 2×ATR + 10 days | +$5,633 | +$472 | −$5 | −$24 |

Result: the 2×ATR stop helps only in the last 12 months and costs over 60 and 24 months, so it's rejected. **The current exits stay.** S3's 2026 problem is the entry signal (dips stopped bouncing back), not the exits, and the per-setup switch is the tool that handles it. The breakeven option stays in the code (`breakeven_after_r`), switched off.

## More symbols tested (2026-11-18): no change adopted yet

Candidate list, fixed before any results:
- **18 ETFs for S3:** SMH, SOXX, IGV, VGT, XBI, IBB, KRE, XHB, ITB, XRT, IYR, VNQ, EWJ, EWZ, FXI, LQD, HYG, SLV.
- **37 large-cap stocks for S2/S4:** MU, AMAT, LRCX, KLAC, ADI, MRVL, NXPI, INTU, NOW, IBM, ACN, GS, MS, BLK, AXP, CAT, DE, HON, GE, LMT, RTX, LOW, SBUX, TGT, BKNG, AMGN, GILD, BMY, ISRG, NEE, DUK, COP, SLB, LIN, T, VZ, CMCSA.

Pass rule, also fixed in advance: (1) the new symbols' trades average above 0R for each setup in both the design and check years; AND (2) the account with them is no worse in at least 3 of 4 windows, including 12 months.

**Rule 1, per trade (average R):**

| | Design 2015–23 | Check 2024–25 | 2026 |
|---|---|---|---|
| S2 current stocks | +0.15 | +0.25 | +0.21 |
| S2 new stocks | **−0.01** | +0.12 | +0.16 |
| S3 current ETFs | +0.19 | +0.17 | −0.08 |
| S3 new ETFs | +0.13 | +0.11 | −0.16 |
| S4 current stocks | +0.46 | +0.42 | −0.27 |
| S4 new stocks | +0.15 | **−0.19** | +0.26 |

**Rule 2, account change vs current watchlist (40/60, current rules):**

| Added | 60 mo | 24 mo | 12 mo | 6 mo | Rule 2 |
|---|---|---|---|---|---|
| New ETFs only | −$1,575 | −$186 | +$71 | +$18 | fail |
| New stocks only | +$794 | +$277 | +$173 | +$9 | pass |
| Both | +$1,461 | +$493 | +$166 | +$8 | pass |

**Verdict:** nothing passes both rules. The new ETFs pass per trade but hurt the account. The new stocks help the account in all 4 windows, but per trade they showed no edge for S2 in the design years. The account gain probably comes from having more signals to choose from (better spread, less idle cash) rather than from the new names being good trades. That could be real, or it could be path luck.

**Downloader hardened:** Yahoo throttling sank whole batches. `prices.daily_bars` now fetches 6 symbols at a time with up to 3 retries.

## Drawdown pause fixed (2026-11-18)

The pause now uses the time-weighted performance index (deposits removed). A test shows investments falling about 20% while deposits push the raw balance up: the new check fires and the old one doesn't. With the current settings (40/60, all safeguards) the worst time-weighted drop was −11.7% (60 months), −11.2% (24), −7.2% (12) and −4.8% (6), so the 15% pause never triggered and results are unchanged. It would have mattered in the higher long-term splits (60/40 and 75/25 reached −19% to −20%).

## Vibe-Trading technical-basic vote tested (2026-11-19)

The vote is Vibe-Trading's own `technical-basic` signal engine with its default settings: EMA(12/26)+ADX(14)>25 trend, Bollinger(20,2)+RSI(14) mean reversion, and OBV vs its 20-day average. Buy, neutral or sell. Rules fixed in advance.

**Test A, the vote as its own setup** (buy when it turns to buy, sell when it stops; plus a 2×ATR stop and a 20-day limit): **fail.**

| | Design 2015–23 | Check 2024–25 | 2026 |
|---|---|---|---|
| Trades | 3,366 | 839 | 347 |
| Average R | +0.04 | −0.01 | +0.19 |
| Winners | 43% | 42% | 50% |

No edge in the check years (Edge score 0), so it isn't a usable signal on its own. 2026 looks good, but 2026 can't be used to choose rules.

**Test B, the vote as a filter** (skip a trade when the vote says sell), average R:

| Setup | Design: current → filtered | Check | 2026 | Verdict |
|---|---|---|---|---|
| S2 | +0.152 → +0.154 | +0.247 → +0.244 | +0.213 → +0.213 | fail (barely any effect) |
| S3 | +0.192 → +0.191 | +0.174 → +0.142 | −0.078 → −0.067 | fail (worse in check) |
| S4 | +0.459 → +0.557 | +0.422 → +0.510 | −0.273 → −0.273 | **pass** (removes 7 of 98 trades) |

S4 account test (40/60): +$1,747 over 60 months; identical over 24, 12 and 6 months (no S4 trades were changed there). It passes the rule, but the evidence is thin: few trades, and the only account difference is in the long window.

**Start-date warning:** the same setup's 60-month result was +$6,730 on 2026-11-18 and +$5,029 on 2026-11-19. Starting one day later shifts deposits and safeguard pauses, and the path diverges. Single-window long results are fragile, so decisions should rest on many start dates, not one.

## Many-start-dates check (2026-11-19)

36 start dates (every 3 months, Jan 2016 to Oct 2024), each run for 24 months with $300 + $250/month and all current rules (goal pause, restart, T-bills, per-setup switch, fixed drawdown pause). 180 simulated accounts. Earnings dates back to 2002, so the earnings rule applies throughout. Starts before 2022 overlap the 2015–23 design years.

| Version | Median profit | Middle half of starts | Worst start | Starts that lost money | Median worst drop | Worst drop (any start) |
|---|---|---|---|---|---|---|
| 20/80 | +6.1% | +3.2% to +12.8% | −7.3% | 8% | −8.9% | −19.2% |
| 40/60 (current) | +11.3% | +5.8% to +14.7% | −3.4% | 8% | −11.1% | −22.0% |
| 40/60 + S4 vote filter | +11.3% | +6.8% to +15.8% | −3.4% | 6% | −11.1% | −22.0% |
| 60/40 | +15.6% | +8.3% to +19.1% | −5.7% | 11% | −14.5% | −25.0% |
| 70/30 | +16.2% | +8.5% to +23.0% | −5.8% | 11% | −16.7% | −27.2% |

Profit = % of money deposited over the 24 months.

- **S4 vote filter: fails the pre-set rule** (beat current in ≥ 60% of starts with a positive median). It was better in 39% of starts, identical in 56% and worse in 6%; median difference 0.00 points, mean +0.55. It rarely changes anything and almost never hurts, but it doesn't clear the bar. **Not adopted.**
- **Split:** 60/40 beat 40/60 in 72% of starts (median +2.1 points; range −5.4 to +16.0). 70/30 beat it in 69% (median +2.4; range −8.8 to +14.9). 20/80 beat it in only 17%. The price of more long-term is deeper drops (median worst drop −14.5% at 60/40 vs −11.1%) and slightly more losing windows (11% vs 8%).
- **By era:** starts in 2022–24 did better across the board (median 40/60 +18.0% vs +8.3% for 2016–21 starts), because 2023–25 was a strong market.
