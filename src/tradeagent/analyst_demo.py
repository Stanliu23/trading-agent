"""Phase 6 done-check: replay 5 past alerts end to end (facts -> analyst -> email), and confirm every number has a source."""

from __future__ import annotations

import json
from datetime import date

import pandas as pd

from tradeagent import analyst, emailer, facts, market, prices
from tradeagent.config import PROJECT_ROOT, Config
from tradeagent.emailer import ActionBox, Card, Email, Footer, Line, Section
from tradeagent.setups.library import get
from tradeagent.setups.stats import stars


def pick(trades: pd.DataFrame) -> list[pd.Series]:
    """Five varied alerts from the replay: 3 buys (S2, S3, S4) and 2 sells (a stop and a time limit)."""
    st = trades[trades.bucket == "short_term"].sort_values("entry_day")
    chosen = []
    for setup_id, reason in (("S2", "target"), ("S3", "signal"), ("S4", "time"), ("S2", "stop"), ("S3", "time")):
        rows = st[(st.setup_id == setup_id) & (st.reason == reason)]
        if len(rows):
            chosen.append(rows.iloc[-1])
    return chosen


def run(config: Config, runner=analyst.claude_runner) -> list[dict]:
    trades = pd.read_csv(PROJECT_ROOT / "data" / "replay" / "trades.csv", parse_dates=["entry_day", "exit_day"])
    stats = {d["setup_id"]: d for d in json.loads((PROJECT_ROOT / "data" / "setup_stats.json").read_text())}
    out_dir = PROJECT_ROOT / "data" / "analyst_demo"
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = pick(trades)
    bars, _ = prices.daily_bars(sorted({r.symbol for r in rows}), "2024-01-01", date.today().isoformat())
    results = []
    for k, r in enumerate(rows, 1):
        s = get(r.setup_id)
        df = bars[r.symbol]
        buy = k <= 3
        if buy:
            day = df.index[df.index.get_loc(r.entry_day) - 1]          # signal close = session before entry
            fs = [facts.signal_fact(r.setup_id, r.symbol, df, day), facts.odds_fact(r.setup_id, stats[r.setup_id]),
                  facts.plan_fact(r.setup_id, r.entry, r.stop if pd.notna(r.stop) else None,
                                  r.target if pd.notna(r.target) else None, s.max_hold_days)]
            purpose = f"a BUY recommendation for {r.symbol} ({r.setup_id})"
        else:
            fs = facts.exit_facts(r.symbol, r.setup_id, r.reason, r.entry_day, r.entry, r.exit_day, r.exit,
                                  r.stop if pd.notna(r.stop) else None, r.target if pd.notna(r.target) else None,
                                  s.max_hold_days)
            purpose = f"a SELL alert for {r.symbol} ({r.reason})"
        w = analyst.write(purpose, fs, config, runner=runner,
                          already_shown=frozenset({"odds", "plan"}) if buy else frozenset())
        if buy:
            st = stats[r.setup_id]
            star = stars(st["edge"], st["confidence"], 5)               # Fit 5: the demo account holds nothing else
            block = Card(tier=st["tier"] or 3, stars=star, action="BUY", symbol=r.symbol, bucket="short-term",
                         size=f"${r.dollars_in:,.2f} (replay)", entry=f"Entry ≈ ${r.entry:,.2f}",
                         stop=f"${r.stop:,.2f}" if pd.notna(r.stop) else None,
                         target=f"${r.target:,.2f}" if pd.notna(r.target) else None, thesis_rule=None,
                         max_loss=f"${r.dollars_in * (r.entry - r.stop) / r.entry:,.2f} at stop" if pd.notna(r.stop) else "–",
                         funding=None, odds=fs[1].text, odds_source=fs[1].source, why_buy=s.logic,
                         why_buy_source=f"setup {r.setup_id}", why=w.why_now.text, why_source=w.why_now.source,
                         stars_detail=f"Edge {st['edge']} · Confidence {st['confidence']} · Fit 5")
            blocks = [block] + w.lines
        else:
            blocks = [ActionBox(f"SELL {r.symbol} · short-term bucket", [w.why_now] + w.lines)]
        em = Email("digest", f"Analyst demo {k}: {purpose}", Line(f"Demo alert {k} of 5: {purpose}.", tone="heading"),
                   [Section("Alert", blocks)], Footer(f"{pd.Timestamp(r.exit_day if not buy else r.entry_day):%b %d %Y} (replay)", None,
                                                      "hypothetical account"))
        problems = emailer.evidence_check(em)
        (out_dir / f"{k}.txt").write_text(emailer.render_text(em, True), encoding="utf-8")
        (out_dir / f"{k}.html").write_text("<!doctype html><meta charset='utf-8'>" + emailer.render_html(em, True), encoding="utf-8")
        results.append({"alert": purpose, "used_ai": w.used_ai, "dropped": w.dropped, "unsourced_numbers": problems})
    return results
