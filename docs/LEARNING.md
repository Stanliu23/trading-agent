# Learning from the paper accounts (designed 2026-11-23, before any data)

Your request: let the Alpaca results teach the agent about decision making and about how strategies are carried out.
The rule since day one still holds: nothing is guessed. So every question below, its minimum number of cases and its
pass rule were written down BEFORE any paper data existed. They are not changed after seeing results; a new
question can be added, dated, but it only counts data from the day it was added.

Two kinds of learning:

1. **Measured and reported (built now).** Every Saturday the report gets a section, "What the paper test is
   teaching", with one line per question. A question shows only its case count until it reaches its minimum (no
   peeking at half-filled numbers); then it gives its answer with a 90% range. Every weekly answer is stored
   (`learning_log`), so the history of what the agent learned, and when, is kept. Answers change no rule by
   themselves: a rule change still needs a backtest and your approval (or the automatic rule in part 2).
2. **Automatic, narrow, only towards caution (designed, OFF until you approve it).** See "Automatic cost update".

## The fill tracker (built now)

At every 16:30 close run, each filled agent order in all three Alpaca paper accounts (main, momentum, low
volatility) is logged in `fill_log` with the price the backtest/simulator ASSUMED for it:

| Order | Assumed price (as in the simulator) | Counts towards |
|---|---|---|
| Main: entry or exit-signal sell sent before 09:30 | that day's official open | Q1 cost |
| Main: entry/exit sent after 09:30 (e.g. a missed premarket run) | none (logged, not counted) | – |
| Main: stop sell | the stop, or the open if the day opened below it | Q2 stops |
| Main: target sell | the target, or the open if the day opened above it | (logged) |
| Main: time-limit sell (last 20 minutes) | that day's close | Q1 cost |
| Experiment sell sent before 09:30 | that day's open | Q1 cost |
| Experiment buy (sent after its sells fill) | that day's open | Q5 rebalance timing |

Cost per fill, in %, positive = worse for us: buys `fill / assumed - 1`, sells `1 - fill / assumed`.
Your own orders are never in `fill_log` (they are Q4). Nothing here places, changes or cancels an order.

## The questions (fixed 2026-11-23)

| # | Question | Minimum | Answer / pass rule |
|---|---|---|---|
| Q1 | Is the real trading cost at or below the 0.1% round trip every backtest assumes? | 30 counted fills | Round trip = 2 x average cost per fill, with a 90% range. Range entirely above 0.10%: **flag**, costs are higher than assumed. Entirely below: lower than assumed (no change: the agent never loosens). Otherwise: consistent with 0.1%. |
| Q2 | Do stops lose more live (15-minute checks, market sells) than the backtest's stop fill? | 10 stop sells | Extra loss per stop in R = (assumed - fill) / (entry - stop). Average above 0.10R with the 90% range above 0: **flag**. |
| Q3 | Do the setups fire about as often live as in the 2015-2025 backtest? | 2 full months | Live signal count per setup vs the backtest's counts over windows of the same length. Outside the backtest's 5th-95th percentile: **flag** (live conditions differ from the test). |
| Q4 | Do your own moves in the main account help? (your sells, and agent buys you cancelled) | 10 moves | Each move vs what the rule would have done (its stop, target, time limit, exit signal; still open = latest close). Report total dollars and share that helped. Helped in >= 60% and total > 0: **your moves helped**. Helped in <= 40% and total < 0: **your moves cost money**. Otherwise mixed. |
| Q5 | Does waiting for the sells to fill before buying (experiments) cost money vs buying at the open? | 20 experiment buys | Average of `fill / open - 1`. Above 0.10% with the 90% range above 0: **flag**. |
| Q6 | Are the experiments doing better or worse than luck alone would explain? | 5 sessions | Since-start return vs SPY, compared with the same-length results in the 2015-2026 test (`research/results/daily_returns.csv`). Inside the middle 90%: within luck, tells us nothing yet. Outside: **flag**. |
| Q7 | Does the per-setup switch skip worse trades than it takes? | 20 skipped and 20 taken | Paper trades (every signal, current exits) since 2026-11-19, split by whether the switch was off on the signal day. Skipped average R below taken by > 0.1R: the switch helped. Above by > 0.1R: **flag**, it skipped better trades. Otherwise no difference yet. |
| Q8 | Do live paper trades match the backtest's average result per setup? | 30 closed paper trades per setup | Live average R vs the 2015-2025 average R. More than 2 standard errors below: **flag**. (The switch already reacts to the last 20; this is the long-run check.) |
| Q9 | Does the system run as designed? | always | Trading days since the start missing a premarket or a close run, and agent orders Alpaca rejected or that failed to send. Any: **flag**. |

Reference numbers for Q3 and Q8 were computed once from 2015-2025 prices and committed
(`research/results/live_reference.json`, made by `research/learning_reference.py`).

## Automatic cost update (designed; OFF until you approve)

When Q1 reaches 30 counted fills and its whole 90% range is above 0.10%, the measured round trip (the upper end of
its range) replaces 0.1% in `backtest.round_trip_cost`, the setup statistics are rebuilt on the Saturday run, and:
- a setup that stops passing the bar is no longer recommended, at once;
- a setup that would newly pass stays as it was until you approve it (the update never makes the agent bolder);
- it is reported in the Saturday email with the before/after numbers, and re-checked every Saturday.
Lower measured costs change nothing. It is not built yet: it will be built only after you approve this rule.

## January review

Go through every question with its answer, plus the Saturday reports since the start. Anything worth changing goes
through the usual backtest and your approval.
