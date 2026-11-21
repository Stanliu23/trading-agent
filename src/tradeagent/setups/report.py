"""Run every setup in the library and write docs/SETUP_STATS.md + data/setup_stats.json."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from tradeagent import prices
from tradeagent.config import PROJECT_ROOT, Config
from tradeagent.setups.library import LIBRARY
from tradeagent.setups.simulate import simulate
from tradeagent.setups.stats import SetupStats, compute_stats


def run_all(config: Config) -> tuple[list[SetupStats], dict[str, list[str]]]:
    bt = config.backtest
    swing_syms = sorted({s for x in LIBRARY if x.kind == "swing" for s in x.universe})
    long_syms = sorted({s for x in LIBRARY if x.kind == "accumulate" for s in x.universe})
    swing_bars, swing_missing = prices.daily_bars(swing_syms, bt.history_start, bt.end)
    long_bars, long_missing = prices.daily_bars(long_syms, bt.long_term_history_start, bt.end)
    results, missing_by_setup = [], {}
    for setup in LIBRARY:
        bars = swing_bars if setup.kind == "swing" else long_bars
        missing = swing_missing if setup.kind == "swing" else long_missing
        trades, tested = [], 0
        for sym in setup.universe:
            df = bars.get(sym)
            if df is None or len(df) < 260:
                continue
            tested += 1
            trades += simulate(df, setup, sym, bt.round_trip_cost, bt.long_term_horizon_days)
        results.append(compute_stats(setup, trades, tested, config))
        missing_by_setup[setup.id] = [s for s in setup.universe if s in missing]
    return results, missing_by_setup


def _pct(x, digits=1, sign=True):
    if x is None:
        return "–"
    return f"{x * 100:+.{digits}f}%" if sign else f"{x * 100:.{digits}f}%"


def _num(x, digits=2):
    return "–" if x is None else f"{x:+.{digits}f}"


def to_markdown(results: list[SetupStats], missing: dict[str, list[str]], config: Config) -> str:
    bt = config.backtest
    lines = [
        "# Setup statistics",
        "",
        "Approved by Stanley on 2026-11-18; re-approved 2026-11-20 after S2 and S4 grew to 77 stocks. Any change to a setup rule or a scoring step needs a new backtest and a new approval.",
        "",
        f"Generated {date.today().isoformat()} by `uv run tradeagent backtest-setups`.",
        f"Data: Yahoo daily bars, adjusted for splits and dividends, from {bt.history_start} to {bt.end}, "
        "fetched through Vibe-Trading's loader.",
        f"Long-term setups use {bt.long_term_history_start} to {bt.end} and are scored on "
        f"{bt.long_term_horizon_days // 252}-year forward returns.",
        f"Costs: {bt.round_trip_cost:.1%} per round trip. Held-out period: short-term trades entered from "
        f"{bt.holdout_start} on; long-term, the last {bt.long_term_holdout_years:g} years of complete entries.",
        "",
        "| Setup | Trades | Loss rate | Avg | Median | 5th pct | Worst | Exp. R | Held-out | Years + | Evidence | Tier | Edge | Conf. | Used? |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in results:
        held = (f"{_num(r.out_metric)}R ({r.out_n})" if r.kind == "swing" else f"{_pct(r.out_metric)} ({r.out_n})")
        lines.append(
            f"| **{r.setup_id}** {r.name} | {r.n} | {_pct(r.loss_rate, 0, sign=False)} | {_pct(r.mean_ret, 2)} | "
            f"{_pct(r.median_ret, 2)} | {_pct(r.tail_ret)} | {_pct(r.worst_ret)} | {_num(r.exp_r)} | {held} | "
            f"{_pct(r.years_positive, 0, sign=False)} | {'pass' if r.passes_evidence else r.evidence_note} | "
            f"{r.tier or '–'} | {r.edge} | {r.confidence} | {'yes' if r.recommendable else 'no (Edge < ' + str(config.evidence.min_edge) + ')' if r.passes_evidence else 'no'} |"
        )
    lines += ["", "## Column meanings", "",
              "- **Loss rate:** share of trades that lost money after costs. Tier 1 needs ≤ 25%, Tier 2 ≤ 40%.",
              "- **5th pct:** 1 in 20 trades did worse than this. Tier 1 needs ≥ −8%, Tier 2 ≥ −15%.",
              "- **Worst:** the single worst trade, usually an earnings gap through the stop. Shown for information; it doesn't set the tier.",
              "- **Exp. R:** average result per unit of risk (1R = the distance from entry to stop).",
              "- **Held-out:** the same metric on trades entered after the cutoff, which the setups were never shaped on.",
              "- **Years +:** share of calendar years whose average trade was positive.",
              "- **Edge / Conf.:** two of the three star sub-scores. **Fit** is added per recommendation: 5 minus the "
              "correlation steps (0.2, 0.4, 0.6, 0.8, 0.9) that the idea's 60-day correlation with your holdings exceeds.",
              f"- **Used?:** a setup is recommended only if it passes the evidence rules and scores at least "
              f"{config.evidence.min_edge} on Edge.",
              "", "## Setup rules", ""]
    from tradeagent.setups.library import LIBRARY as LIB
    for s in LIB:
        lines.append(f"- **{s.id} {s.name}** ({s.bucket.replace('_', '-')}, {len(s.universe)} symbols): {s.rule}")
        for note in s.notes:
            lines.append(f"  - Note: {note}")
    gaps = {k: v for k, v in missing.items() if v}
    if gaps:
        lines += ["", "## Missing data", ""] + [f"- {k}: {', '.join(v)}" for k, v in gaps.items()]
    lines += ["", "## Known limits", "",
              "- **Survivorship bias:** the stock list is today's large caps, so S2 and S4 (and S1's stock half) look "
              "better than they would have in real time.",
              "- Trades on different stocks that open on the same day are correlated, so the real sample is smaller than the trade count.",
              "- Daily bars can't show which of stop and target was hit first in a day. The simulator always assumes the stop.",
              "- Live, the agent skips short-term stock entries when earnings fall before the planned exit. The free data has no "
              "historical earnings dates, so these stats still include trades held through earnings.",
              "- Long-term windows overlap (one starts every month), so their trade count overstates the independent evidence."]
    return "\n".join(lines) + "\n"


def write_report(config: Config, root: Path = PROJECT_ROOT) -> Path:
    results, missing = run_all(config)
    out_md = root / "docs" / "SETUP_STATS.md"
    out_md.write_text(to_markdown(results, missing, config), encoding="utf-8")
    out_json = root / "data" / "setup_stats.json"
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps([r.as_dict() for r in results], indent=2), encoding="utf-8")
    return out_md
