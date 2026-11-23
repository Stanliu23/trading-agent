"""Score the strategy tournament with the pass bar fixed in strategy_tournament.py. Writes research/results/summary.md."""

from pathlib import Path

import pandas as pd


def md(df: pd.DataFrame, index: bool = True) -> str:
    """Markdown table without extra packages."""
    d = df.reset_index() if index else df
    fmt = lambda v: f"{v:.1f}" if isinstance(v, float) else str(v)
    lines = ["| " + " | ".join(map(str, d.columns)) + " |", "|" + "---|" * len(d.columns)]
    lines += ["| " + " | ".join(fmt(v) for v in row) + " |" for row in d.itertuples(index=False)]
    return "\n".join(lines)

R = Path(__file__).resolve().parent / "results"
NAMES = {"TODAY": "Today's rules", "MOM": "Stock momentum", "TREND": "ETF trend timing", "DON": "Donchian breakout",
         "S3F": "S3 with market filter", "SECT": "Sector rotation", "REV": "Short-term reversal",
         "LOWV": "Low volatility", "L1 (index funds)": "Index funds only (L1)", "SPY": "SPY"}


def main():
    s1 = pd.read_csv(R / "step1_periods.csv")
    s2 = pd.read_csv(R / "step2_starts.csv", dtype={"ratio": str})
    cond = pd.read_csv(R / "conditions.csv")
    out = []
    p1 = s1.pivot(index="strategy", columns="period", values="net_profit_pct")
    base = s2[(s2.strategy == "TODAY") & (s2.ratio == "40/60")].set_index("start")
    rows = []
    for s in [x for x in p1.index if x != "TODAY"]:
        c = s2[(s2.strategy == s) & (s2.ratio == "40/60")].set_index("start")
        diff = c.gain_pct - base.gain_pct
        dd = c.worst_drop_pct - base.worst_drop_pct
        ok1 = p1.at[s, "design"] > 0 and p1.at[s, "check"] > 0
        ok2 = (diff > 1e-9).mean() >= 0.6 and diff.median() > 0 and dd.median() >= -1
        ok3 = p1.at[s, "final"] >= 0
        rows.append({"strategy": s, "design %": p1.at[s, "design"], "check %": p1.at[s, "check"], "step 1": ok1,
                     "better in": f"{(diff > 1e-9).mean():.0%}", "median gain pts": round(diff.median(), 2),
                     "median drop pts": round(dd.median(), 2), "step 2": ok2, "2026 %": p1.at[s, "final"],
                     "step 3": ok3, "PASS": ok1 and ok2 and ok3, "_med": diff.median()})
    t = pd.DataFrame(rows)
    passed = t[t.PASS].sort_values("_med", ascending=False)
    picks = list(passed.strategy[:2])
    out.append("# Strategy tournament results\n")
    out.append(f"Today's rules, short-term sleeve: design {p1.at['TODAY', 'design']:+.1f}%, check "
               f"{p1.at['TODAY', 'check']:+.1f}%, 2026 {p1.at['TODAY', 'final']:+.1f}% ($1,000, no deposits).\n")
    real = s2[s2.strategy == "TODAY_REAL_SIM"].set_index("start")
    out.append(f"Model check: rebuilt 40/60 account vs the real simulator, median gain {base.gain_pct.median():.1f}% vs "
               f"{real.gain_pct.median():.1f}%, median worst drop {base.worst_drop_pct.median():.1f}% vs "
               f"{real.worst_drop_pct.median():.1f}%.\n")
    out.append("## Pass bar at 40/60\n")
    out.append(md(t.drop(columns="_med").assign(strategy=t.strategy.map(NAMES)), index=False))
    out.append(f"\n**Picks (pick rule):** {', '.join(NAMES[p] for p in picks) if picks else 'none passed'}\n")

    out.append("## Long/short splits (36 starts, $300 + $250/month, 24 months)\n")
    out.append("Median gain on money deposited / median worst drop / share of starts better than today's 40/60.\n")
    rows = []
    for s in ["TODAY"] + [x for x in p1.index if x != "TODAY"]:
        r = {"strategy": NAMES[s]}
        for ratio in ["100/0", "80/20", "60/40", "40/60", "20/80", "0/100"]:
            c = s2[(s2.strategy == s) & (s2.ratio == ratio)].set_index("start")
            better = ((c.gain_pct - base.gain_pct) > 1e-9).mean()
            r[ratio] = f"{c.gain_pct.median():+.1f}% / {c.worst_drop_pct.median():.1f}% / {better:.0%}"
        rows.append(r)
    out.append(md(pd.DataFrame(rows), index=False))

    out.append("\n## Market conditions (short-term sleeve alone, Jan 2015 - Nov 2026)\n")
    a = cond[cond.annualised_pct.notna()].pivot(index="strategy", columns="condition", values="annualised_pct")
    a.index = a.index.map(NAMES)
    out.append("Annualised return on the days in each condition:\n")
    out.append(md(a.round(1)))
    e = cond[cond.total_pct.notna()]
    for col, label in (("total_pct", "Return in each episode"), ("worst_drop_pct", "Worst drop in each episode")):
        p = e.pivot(index="strategy", columns="condition", values=col)
        p.index = p.index.map(NAMES)
        out.append(f"\n{label} (%):\n")
        out.append(md(p.round(1)))
    (R / "summary.md").write_text("\n".join(out) + "\n")
    print("\n".join(out))


if __name__ == "__main__":
    main()
