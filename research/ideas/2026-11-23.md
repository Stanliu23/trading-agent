# Ideas from GitHub, week of 2026-11-23
## 1. Volatility-scaled share of the long-term bucket
- What: Hold less of the stock index funds (VTI/QQQ/SCHD) and park the rest in BIL when recent market volatility is high, scaled smoothly with a cap of 100% so there is never leverage.
- Source: https://github.com/pst-group/pysystemtrade (volatility-targeting code, formerly robcarver17/pysystemtrade); paper: Moreira and Muir, "Volatility-Managed Portfolios", Journal of Finance 2017 (critique: Cederburg et al. 2020, gains shrink out of sample, drops still shrink).
- License: GPL-3.0; idea only, we write our own code.
- Better than ours because: today the long-term bucket is always fully in index funds, so index-only (100/0) had a -19.6% median worst drop vs -13.1% for today's 40/60; scaling exposure by trailing volatility has cut equity drawdowns in long samples (Harvey et al. 2018), and unlike our failed binary VIX gates it is continuous. Caveat: related VIX-high gating failed on S2, and the paper's return gain is disputed, so it may only pass on the drop rule.
- Would change: src/tradeagent/risk.py (new vol_scale function next to split_deposit), the long-term buy path in src/tradeagent/papertrade.py, config.yaml (new vol_target block, off by default), research/ (new test script).
- How it would be tested: Fixed before running: scale = min(1, 15% / (SPY 20-day realised volatility, annualised)), read at the close; design 2015-2023, check 2024-2025, final 2026; 36 quarterly starts, 24 months each; pass if the account beats today's rules in at least 60% of starts, median gain positive, median worst drop no more than 1 point deeper.
- Verdict: can build
## 2. Trailing stop for the 52-week-high breakout (S2)
- What: Replace S2's fixed 4xATR target with a trailing stop that sits 3xATR below the highest close since entry (never lower than the initial 2xATR stop), keeping the 20-day limit.
- Source: https://www.freqtrade.io/en/stable/strategy-callbacks/ (custom_stoploss, https://github.com/freqtrade/freqtrade); paper: Kaminski and Lo, "When Do Stop-Loss Rules Stop Losses?", Journal of Financial Markets 2014 (stops add value in trending/momentum regimes); chandelier exit, LeBeau/Elder, also used in Clenow, Following the Trend.
- License: GPL-3.0 for freqtrade; idea only, we write our own code (the chandelier rule itself is textbook).
- Better than ours because: our exit study found winners fall from a best point of +1.92R to a close of +1.53R and that only 2% reach +3R with a fixed target, but the menu never included a trailing stop (only stop x target x time), and breakeven-after-1R failed because it cuts winners early; a 3xATR trail lets winners run while locking in gains, matching S2's momentum logic. Risk: it may repeat the menu's over-fit pattern, so only ONE pre-set variant is tested.
- Would change: src/tradeagent/setups/library.py (Setup gets a trail_atr field, S2 uses it), the backtest and paper exit code that handles stop and target (src/tradeagent/papertrade.py and the backtest engine), tests.
- How it would be tested: The existing exit-study pass rule: on 2024-25 at least +0.05R per trade better than current S2 exits, then the 36-start account check (40/60, $300 + $250/month, 24 months) better in at least 60% of starts with positive median and median worst drop no more than 1 point deeper; 2026 reported only.
- Verdict: can build
