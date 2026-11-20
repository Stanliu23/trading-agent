"""Macro signals as trade inputs, trusted only on evidence, re-scored every week (rules: docs/REPLAY_FINDINGS.md,
"Macro signals as trade inputs"). Macro may only REDUCE risk: halve or skip a buy, never start one.

Two kinds of input:
- market stress (VIX, dollar via UUP, oil via USO): testable on years of history, scored per setup;
- news stories: no usable history, so every confirmed story is logged and its 5-session effect vs SPY recorded;
  a factor earns trust from that record.
Every score is stored (``macro_scores``, ``macro_news``) so the record of what was trusted, when and why is kept.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from typing import Optional

import numpy as np
import pandas as pd

STRESS_SYMBOLS = ("^VIX", "UUP", "USO")
CONDITIONS = ("VIX high", "VIX spike", "Dollar surge", "Oil shock")
MIN_ON_DESIGN, MIN_ON_CHECK, MIN_HARM = 30, 10, -0.10
NEWS_MIN_STORIES, NEWS_MEDIAN, NEWS_SHARE, NEWS_DAYS = 20, -0.01, 0.65, 5


def conditions(bars: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Each stress condition per day, as known at that day's close."""
    vix, uup, uso = bars["^VIX"]["close"], bars["UUP"]["close"], bars["USO"]["close"]
    q = lambda s, p: s.rolling(252, min_periods=200).quantile(p)
    u20, o20 = uup.pct_change(20), uso.pct_change(20).abs()
    out = pd.DataFrame({"VIX high": vix > q(vix, .8), "VIX spike": vix.pct_change(5) >= .25,
                        "Dollar surge": u20 > q(u20, .9), "Oil shock": o20 > q(o20, .9)})
    return out.fillna(False).astype(bool)


@dataclass
class Score:
    setup_id: str
    condition: str
    n_on: tuple[int, int]
    r_on: tuple[float, float]
    r_off: tuple[float, float]
    passes: bool                 # rules 1 and 2
    action: Optional[str]        # "half" | "skip" | None
    reason: str


def periods(as_of: date) -> tuple[pd.Timestamp, pd.Timestamp, pd.Timestamp]:
    """(design start, check start, end): design = 2015 to 2 years ago, check = the last 2 years."""
    end = pd.Timestamp(as_of)
    return pd.Timestamp("2015-01-01"), end - pd.DateOffset(years=2), end


def score(trades: pd.DataFrame, cond: pd.DataFrame, as_of: date) -> list[Score]:
    """``trades``: setup_id, signal_day, r (one row per past trade with the current exits)."""
    d0, c0, end = periods(as_of)
    out = []
    t = trades[(trades.signal_day >= d0) & (trades.signal_day < end)].copy()
    on_all = cond.reindex(t.signal_day.values).fillna(False)
    for sid, g in t.groupby("setup_id"):
        for k in CONDITIONS:
            on = on_all.loc[g.signal_day.values, k].to_numpy(bool)
            n, ron, roff = [], [], []
            for lo, hi in ((d0, c0), (c0, end)):
                m = ((g.signal_day >= lo) & (g.signal_day < hi)).to_numpy()
                n.append(int((m & on).sum()))
                ron.append(float(g.r[m & on].mean()) if (m & on).any() else float("nan"))
                roff.append(float(g.r[m & ~on].mean()) if (m & ~on).any() else float("nan"))
            enough = n[0] >= MIN_ON_DESIGN and n[1] >= MIN_ON_CHECK
            harm = all(np.isfinite(a - b) and a - b <= MIN_HARM for a, b in zip(ron, roff))
            action = ("skip" if all(x <= 0 for x in ron) else "half") if enough and harm else None
            reason = ("passes: " + action if action else
                      f"too few cases ({n[0]} design, {n[1]} check)" if not enough else "no consistent harm")
            out.append(Score(sid, k, tuple(n), tuple(round(x, 3) for x in ron), tuple(round(x, 3) for x in roff),
                             enough and harm, action, reason))
    return out


def multipliers(active: dict[tuple[str, str], str], cond: pd.DataFrame) -> dict[str, pd.Series]:
    """active: (setup, condition) -> action. Setup id -> daily multiplier (the strictest active condition wins)."""
    out: dict[str, pd.Series] = {}
    for (sid, k), action in active.items():
        m = cond[k].map({True: 0.0 if action == "skip" else 0.5, False: 1.0})
        out[sid] = m if sid not in out else np.minimum(out[sid], m)
    return out


# --- storage ---------------------------------------------------------------------------------

SCHEMA = """
CREATE TABLE IF NOT EXISTS macro_scores (
    scored_at TEXT NOT NULL, setup_id TEXT NOT NULL, condition TEXT NOT NULL, detail TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('on','off')), action TEXT, change TEXT,
    PRIMARY KEY (scored_at, setup_id, condition));
CREATE TABLE IF NOT EXISTS macro_news (
    story_key TEXT NOT NULL, day TEXT NOT NULL, factor TEXT NOT NULL, symbol TEXT NOT NULL, publishers TEXT NOT NULL,
    ret5_vs_spy REAL, PRIMARY KEY (story_key, symbol));
"""


def ensure(conn) -> None:
    conn.executescript(SCHEMA)


def active(conn) -> dict[tuple[str, str], str]:
    """The latest status of every (setup, condition)."""
    ensure(conn)
    rows = conn.execute("SELECT s.setup_id, s.condition, s.status, s.action FROM macro_scores s JOIN "
                        "(SELECT setup_id, condition, MAX(scored_at) m FROM macro_scores GROUP BY setup_id, condition) l "
                        "ON s.setup_id = l.setup_id AND s.condition = l.condition AND s.scored_at = l.m").fetchall()
    return {(r[0], r[1]): r[3] for r in rows if r[2] == "on"}


def record(conn, scores: list[Score], account_ok: dict[tuple[str, str], bool], now: datetime) -> list[str]:
    """Store this week's scores and apply the switch rules. Returns plain-English changes for the weekly email.

    On: passes rules 1-2 AND the account check (``account_ok``). Off: fails rule 1 or 2."""
    ensure(conn)
    before = active(conn)
    changes = []
    for s in scores:
        key = (s.setup_id, s.condition)
        was = key in before
        on = s.passes and (account_ok.get(key, False) or (was and before[key] == s.action))
        change = None
        if on and not was:
            change = f"ON: {s.condition} now {'halves' if s.action == 'half' else 'skips'} {s.setup_id} buys ({s.reason})."
        elif was and not on:
            change = f"OFF: {s.condition} no longer changes {s.setup_id} buys ({s.reason})."
        elif s.passes and not on:
            change = f"Not switched on: {s.condition} for {s.setup_id} passes per trade but failed the account check."
        if change:
            changes.append(change)
        conn.execute("INSERT OR REPLACE INTO macro_scores VALUES (?,?,?,?,?,?,?)",
                     (now.isoformat(timespec="seconds"), s.setup_id, s.condition, json.dumps(asdict(s)),
                      "on" if on else "off", s.action if on else None, change))
    conn.commit()
    return changes


# --- news ledger -------------------------------------------------------------------------------

def log_story(conn, key: str, day: date, factor: str, symbols: list[str], publishers: list[str]) -> None:
    ensure(conn)
    conn.executemany("INSERT OR IGNORE INTO macro_news(story_key, day, factor, symbol, publishers) VALUES (?,?,?,?,?)",
                     [(key, day.isoformat(), factor, s, ", ".join(sorted(publishers))) for s in symbols])
    conn.commit()


def fill_outcomes(conn, bars: dict[str, pd.DataFrame]) -> int:
    """Record each logged symbol's 5-session return vs SPY once 5 sessions have passed."""
    ensure(conn)
    spy = bars["SPY"]["close"]
    n = 0
    for key, day, sym in conn.execute("SELECT story_key, day, symbol FROM macro_news WHERE ret5_vs_spy IS NULL").fetchall():
        if sym not in bars:
            continue
        c = bars[sym]["close"]
        idx = c.index[c.index >= pd.Timestamp(day)]
        if len(idx) <= NEWS_DAYS:
            continue
        a, b = idx[0], idx[NEWS_DAYS]
        r = (c[b] / c[a] - 1) - (spy.get(b, np.nan) / spy.get(a, np.nan) - 1)
        if np.isfinite(r):
            conn.execute("UPDATE macro_news SET ret5_vs_spy=? WHERE story_key=? AND symbol=?", (float(r), key, sym))
            n += 1
    conn.commit()
    return n


def news_trust(conn) -> dict[str, dict]:
    """Per factor: stories so far, median 5-day return vs SPY, share negative, trusted or not."""
    ensure(conn)
    df = pd.read_sql_query("SELECT story_key, factor, ret5_vs_spy FROM macro_news WHERE ret5_vs_spy IS NOT NULL", conn)
    out = {}
    for f, g in df.groupby("factor"):
        per_story = g.groupby("story_key").ret5_vs_spy.median()
        med, neg = float(per_story.median()), float((per_story < 0).mean())
        out[f] = {"stories": int(len(per_story)), "median": med, "negative": neg,
                  "trusted": len(per_story) >= NEWS_MIN_STORIES and med <= NEWS_MEDIAN and neg >= NEWS_SHARE}
    return out


def news_blocked(conn, today: date, sessions_back: list[date]) -> dict[str, str]:
    """Symbols touched by a confirmed story of a trusted factor in the last 5 sessions -> why (no new buys)."""
    trusted = {f for f, v in news_trust(conn).items() if v["trusted"]}
    if not trusted:
        return {}
    since = min(sessions_back[-NEWS_DAYS:]).isoformat() if sessions_back else today.isoformat()
    rows = conn.execute("SELECT symbol, factor, day FROM macro_news WHERE day >= ?", (since,)).fetchall()
    return {r[0]: f"{r[1]} story on {r[2]}" for r in rows if r[1] in trusted}
