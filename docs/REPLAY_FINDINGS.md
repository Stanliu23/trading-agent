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
