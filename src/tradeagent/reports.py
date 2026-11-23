"""Build the real emails from the shadow account (layouts: docs/EMAILS.md)."""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Optional

import pandas as pd

from tradeagent import analyst, facts, market_calendar, risk
from tradeagent.account import AccountState
from tradeagent.config import Config, active_profile
from tradeagent.emailer import (ActionBox, Card, Email, Footer, Line, Section, Table, pct, subject_line, usd)
from tradeagent.setups.library import get
from tradeagent.setups.stats import stars

TIER_LABEL = {1: "Tier 1 (low risk)", 2: "Tier 2 (medium risk)", 3: "Tier 3 (high risk)"}


def _src(state: AccountState) -> str:
    return f"{state.label} {state.day:%m-%d}"


def footer(state: AccountState) -> Footer:
    return Footer(f"close {state.day:%b %d}", None, state.source)


def _bucket_table(state: AccountState, config: Config) -> Table:
    d = state.sim.daily.iloc[-1]
    v = state.value()
    profile = active_profile(config, ever_reached_switch=state.sim.daily["profile"].iloc[-1] == "moderate")
    rows = []
    for name, val in (("Long-term", d["lt_value"] + d["cash_lt"]), ("Short-term", d["st_value"] + d["cash_st"])):
        band = getattr(profile.buckets, "long_term" if name == "Long-term" else "short_term")
        share = val / v if v else 0
        ok = band.min - 1e-9 <= share <= band.max + 1e-9
        rows.append([name, f"{share:.0%}", f"{band.target:.0%}", f"{band.min:.0%}–{band.max:.0%}", "✓" if ok else "out of band"])
    return Table(["Bucket", "Now", "Target", "Band", ""], rows, _src(state))


def account_section(state: AccountState, config: Config) -> Section:
    daily = state.sim.daily
    dep_today = sum(a for d, a, _ in state.sim.deposits if d == state.day)
    v = state.value()
    prev = float(daily["value"].iloc[-2]) if len(daily) > 1 else v - dep_today   # day one: nothing before the deposit
    change = v - prev - dep_today
    spy = state.bars["SPY"]["close"]
    spy_ret = float(spy.loc[:state.day].iloc[-1] / spy.loc[:state.day].iloc[-2] - 1)
    perf = daily["perf_index"]
    dd = float(perf.iloc[-1] / perf.cummax().iloc[-1] - 1)
    cash = float(daily["cash_lt"].iloc[-1] + daily["cash_st"].iloc[-1])
    profile = active_profile(config, ever_reached_switch=daily["profile"].iloc[-1] == "moderate")
    lines = [Line(f"Value {usd(v)} ({usd(change, True)}, {pct(change / prev if prev else 0)}) · SPY {pct(spy_ret)}",
                  _src(state), "up" if change >= 0 else "down"),
             _bucket_table(state, config),
             Line(f"{'Cash (kept as cash in the paper test)' if state.paper_note else 'Cash parked in ' + (config.cash.park_idle_in or 'cash')} "
                  f"{usd(cash)} · drop from peak {pct(dd)} "
                  f"(pause at −{profile.drawdown_pause:.0%})", _src(state))]
    if dep_today:
        lines.append(Line(f"Deposit today {usd(dep_today)} was split by the 40/60 rule.", _src(state)))
    return Section("Account", lines)


def _buy_card(state: AccountState, order: dict, config: Config, runner, conn) -> Card:
    s = get(order["setup_id"])
    st = state.stats[order["setup_id"]]
    df = state.bars[order["symbol"]]
    close = float(df.loc[:state.day, "close"].iloc[-1])
    v = state.value()
    if s.kind == "swing":
        fs = [facts.signal_fact(s.id, order["symbol"], df, state.day), facts.odds_fact(s.id, st),
              facts.plan_fact(s.id, close, order["stop"], order["target"], s.max_hold_days)]
        exit_day = risk.planned_exit_day(state.day.date(), s.max_hold_days) if s.max_hold_days else None
        ef = facts.earnings_fact(order["symbol"], state.next_earnings(order["symbol"]), exit_day)
        if ef:
            fs.append(ef)
        w = analyst.write(f"a BUY recommendation for {order['symbol']} ({s.id})", fs, config, runner=runner, conn=conn,
                          already_shown=frozenset({"odds", "plan"}))
        stop_frac = (close - order["stop"]) / close
        max_loss = order["dollars"] * stop_frac
        cap = st and (state.sim.daily["profile"].iloc[-1])
        return Card(tier=st["tier"] or 3, stars=stars(st["edge"], st["confidence"], 5), action="BUY", symbol=order["symbol"],
                    bucket="short-term", size=f"{usd(order['dollars'])} = {order['dollars'] / v:.1%} of account",
                    entry=f"Entry ≈ {usd(close)}", stop=f"{usd(order['stop'])} (−{stop_frac:.1%})",
                    target=f"{usd(order['target'])} (+{order['target'] / close - 1:.1%})" if order["target"] else None,
                    thesis_rule=None, max_loss=f"{usd(max_loss)} = {max_loss / v:.1%} of account at stop",
                    funding=f"Sell {usd(order['dollars'])} of {config.cash.park_idle_in} first" if config.cash.park_idle_in else None,
                    odds=fs[1].text, odds_source=fs[1].source, why_buy=s.logic, why_buy_source=f"setup {s.id}",
                    why=w.why_now.text, why_source=w.why_now.source,
                    stars_detail=f"Edge {st['edge']} · Confidence {st['confidence']} · Fit 5")
    # long-term
    l1 = state.stats["L1"]
    return Card(tier=l1["tier"] or 3, stars=stars(l1["edge"], l1["confidence"], 5), action="BUY", symbol=order["symbol"],
                bucket="long-term", size=f"{usd(order['dollars'])} = {order['dollars'] / v:.1%} of account",
                entry="at the open", stop=None, target=None,
                thesis_rule="never on price noise; only a measured thesis break", max_loss="no stop: long-term holding",
                funding="from deposits (long-term share)", odds=f"{l1['n']} three-year windows since 2005: "
                f"{1 - l1['loss_rate']:.0%} positive, 1 in 20 worse than {l1['tail_ret']:.1%}.", odds_source="setup L1",
                why_buy=get("L1").logic, why_buy_source="setup L1",
                why=f"{order['symbol']} is the long-term fund you hold least of.", why_source=_src(state),
                stars_detail=f"Edge {l1['edge']} · Confidence {l1['confidence']} · Fit 5")


def _sell_box(state: AccountState, sell: dict, config: Config, runner, conn) -> ActionBox:
    p = sell["position"]
    s = get(p.setup_id)
    nxt = market_calendar.next_session(state.day.date()).day
    when = f"at {nxt:%a %b %d}'s open" if sell["when"] == "open" else f"before {nxt:%a %b %d}'s close"
    fs = facts.exit_facts(p.symbol, p.setup_id, sell["reason"], p.entry_day, p.entry, state.day, sell["price"],
                          p.stop, p.target, s.max_hold_days, pending=True)
    if sell["reason"] == "time":
        fs[0] = analyst.Fact("exit", f"{nxt:%a %b %d} is day {s.max_hold_days} of {s.max_hold_days} for this "
                                     f"{s.name.lower()} trade.", f"setup {s.id} rules")
    else:
        fs[0] = analyst.Fact("exit", f"{p.symbol} closed back above its 20-day average on {state.day:%b %d}, "
                                     f"which is this setup's exit rule.", f"setup {s.id} rules")
    w = analyst.write(f"a SELL alert for {p.symbol} ({sell['reason']})", fs, config, runner=runner, conn=conn)
    lines = [w.why_now] + w.lines + [Line(f"All {p.qty:.4f} shares, about {usd(sell['value'])}; proceeds go back to "
                                          f"{config.cash.park_idle_in or 'cash'}.", _src(state))]
    return ActionBox(f"SELL {p.symbol} {when} · short-term bucket", lines)


def safeguard_lines(state: AccountState) -> list[Line]:
    out = []
    if state.sim.goal_paused:
        note = next((n for n in reversed(state.sim.notes) if n.startswith("Goal check")), "")
        out.append(Line("Short-term buys are paused by the goal check: " + note.replace("Goal check ", "since ", 1),
                        _src(state), "down"))
    if state.sim.drawdown_paused:
        out.append(Line("New short-term trades are paused: the account is 15% or more below its peak.", _src(state), "down"))
    for n in state.macro_notes:
        out.append(Line(n, "macro trust score", "muted"))
    switched = state.sim.switched_off_now
    if switched:
        out.append(Line(f"Switched off by their own paper record: {', '.join(switched)}.", _src(state), "muted"))
    return out


def digest(state: AccountState, config: Config, *, macro_lines: Optional[list[Line]] = None,
           runner=analyst.claude_runner, conn=None, system_lines: Optional[list[Line]] = None) -> Email:
    sells = [_sell_box(state, s, config, runner, conn) for s in state.sells_tomorrow()]
    st_orders = [o for o in state.sim.next_orders if o["bucket"] == "short_term"]
    lt_orders = [o for o in state.sim.next_orders if o["bucket"] == "long_term"]
    by_tier: dict[int, list[Card]] = defaultdict(list)
    for o in st_orders:
        card = _buy_card(state, o, config, runner, conn)
        by_tier[card.tier].append(card)
    buy_blocks: list = []
    for t in (1, 2, 3):
        if by_tier.get(t):
            buy_blocks.append(Line(TIER_LABEL[t] + ":", tone="heading"))
            buy_blocks += by_tier[t]
        else:
            buy_blocks.append(Line(f"{TIER_LABEL[t]}: none qualified today.", tone="muted"))
    n_actions = len(sells) + len(st_orders) + len(lt_orders)
    lead_parts = [f"sell {b.title.split()[1]}" for b in sells] + [f"buy {o['symbol']}" for o in st_orders + lt_orders]
    lead = (Line(f"{n_actions} action{'s' if n_actions != 1 else ''} for tomorrow: " + ", ".join(lead_parts) + ".",
                 _src(state), "strong") if n_actions else Line("No actions for tomorrow.", _src(state), "strong"))
    sections = [account_section(state, config)]
    if state.paper_note:
        sections.append(Section("Paper trading", [Line(state.paper_note, "agent rules")]
                                + [Line(e, _src(state)) for e in state.paper_events]))
    guards = safeguard_lines(state)
    if guards:
        sections.append(Section("Safeguards", guards))
    sections.append(Section("Sells for the next session (do these first: they free up cash)",
                            sells or [Line("None.", tone="muted")]))
    sections.append(Section("Buys for the next session", buy_blocks))
    if lt_orders:
        sections.append(Section("Long-term", [_buy_card(state, o, config, runner, conn) for o in lt_orders]))
    if macro_lines:
        sections.append(Section("Macro on your holdings", macro_lines))
    watch = []
    for p in state.sim.open_positions:
        ne = state.next_earnings(p.symbol)
        if ne and (ne - state.day.date()).days <= 7:
            watch.append(Line(f"{p.symbol} reports earnings {ne:%b %d}.", "Yahoo earnings calendar"))
        px = state.price(p.symbol)
        if p.stop and px and (px - p.stop) / px <= 0.015:
            watch.append(Line(f"{p.symbol} is {(px - p.stop) / px:.1%} above its stop ({usd(p.stop)}).", _src(state)))
    if watch:
        sections.append(Section("Watch next", watch))
    if system_lines:
        sections.append(Section("System", system_lines))
    v = state.value()
    dep_today = sum(a for d, a, _ in state.sim.deposits if d == state.day)
    prev = float(state.sim.daily["value"].iloc[-2]) if len(state.sim.daily) > 1 else v - dep_today
    ch = v - prev - dep_today
    spy = state.bars["SPY"]["close"].loc[:state.day]
    subj = subject_line("digest", [f"{state.day:%a %b %d}", usd(v), f"{usd(ch, True)} ({pct(ch / prev if prev else 0)})",
                                   f"SPY {pct(float(spy.iloc[-1] / spy.iloc[-2] - 1))}",
                                   f"{n_actions} action{'s' if n_actions != 1 else ''}"], config.mode == "shadow")
    return Email("digest", subj, lead, sections, footer(state))


# --- 08:00 premarket ----------------------------------------------------------------

def premarket(state: AccountState, config: Config, *, macro_lines: Optional[list[Line]] = None) -> Email:
    """Three lines before the open: today's actions (decided at yesterday's close), overnight macro, what to watch."""
    today = market_calendar.next_session(state.day.date()).day
    sells = state.sells_tomorrow()
    buys = state.sim.next_orders
    acts = ([f"sell {s['position'].symbol} ({'open' if s['when'] == 'open' else 'before close'})" for s in sells]
            + [f"buy {o['symbol']} ({o['bucket'].replace('_', '-')})" for o in buys])
    lead = Line((f"{len(acts)} action{'s' if len(acts) != 1 else ''} today: " + ", ".join(acts) + " (details in last night's digest).")
                if acts else "No actions today.", _src(state), "strong")
    lines = list(macro_lines or [Line("No confirmed macro news with a measured link to your holdings overnight.", tone="muted")])[:3]
    watch = [f"{p.symbol} reports earnings {state.next_earnings(p.symbol):%b %d}" for p in state.sim.open_positions
             if state.next_earnings(p.symbol) and (state.next_earnings(p.symbol) - today).days <= 2]
    sections = [Section("Overnight", lines)]
    if watch:
        sections.append(Section("Today", [Line(" · ".join(watch) + ".", "Yahoo earnings calendar")]))
    subj = subject_line("premarket", [f"{today:%a %b %d}", usd(state.value()), f"{len(acts)} action{'s' if len(acts) != 1 else ''}"],
                        config.mode == "shadow")
    return Email("premarket", subj, lead, sections, footer(state))


# --- 15-minute urgent alerts --------------------------------------------------------------

def urgent(state: AccountState, quotes: dict, config: Config, *, sigmas: Optional[dict[str, float]] = None,
           filing_events: Optional[list[tuple[str, str, object]]] = None, fired: Optional[set[str]] = None,
           now=None, executed: Optional[list] = None) -> tuple[Optional[Email], list[str]]:
    """One email for everything urgent found in this check, or None. Returns (email, keys to record as fired).

    quotes: symbol -> market.Quote; sigmas: symbol -> daily sigma; filing_events: (symbol, kind, impact.Impact)."""
    from tradeagent import triggers as tg

    now = now or pd.Timestamp.now(tz="America/New_York")
    day = now.date()
    fired = set(fired or ())
    events, blocks = [], []
    for p in state.sim.open_positions:
        q = quotes.get(p.symbol)
        if q is None:
            continue
        hit = None if executed is not None else tg.stop_or_target(p.symbol, q.price, p.stop, p.target, day)
        if hit and hit.key not in fired:
            word = "stop" if hit.rule == "stop_hit" else "target"
            level = p.stop if word == "stop" else p.target
            value = p.qty * q.price
            events.append((hit.key, f"SELL {p.symbol}", f"{word} hit"))
            blocks.append(ActionBox(f"SELL {p.symbol} now · {p.bucket.replace('_', '-')} bucket", [
                Line(f"{p.symbol} is at {usd(q.price)}, {'at or below its stop' if word == 'stop' else 'at or above its target'} "
                     f"of {usd(level)}.", f"Yahoo quote {now:%H:%M}", "down" if word == "stop" else "up"),
                Line(f"Bought at {usd(p.entry)}: {pct(q.price / p.entry - 1)} so far. All {p.qty:.4f} shares, about {usd(value)}.",
                     f"Yahoo quote {now:%H:%M}"),
                Line(f"Rule: setup {p.setup_id} sells at its {word}.", f"setup {p.setup_id} rules")]))
        sig = (sigmas or {}).get(p.symbol)
        mv = tg.move(p.symbol, q.price, q.prev_close, sig, day, config)
        if mv and mv.urgent and mv.key not in fired:
            events.append((mv.key, p.symbol, f"{mv.detail['sigmas']:+.1f}σ move"))
            blocks.append(Line(f"{p.symbol} {pct(mv.detail['return'])} today, a {mv.detail['sigmas']:+.1f}σ move for it "
                               f"(its own last {config.triggers.sigma_lookback_days} days). No sell rule has fired; "
                               f"stop {usd(p.stop) if p.stop else 'none (long-term)'}.", f"Yahoo quote {now:%H:%M}",
                               "down" if mv.detail["return"] < 0 else "up"))
    for sym, filing_id, imp in filing_events or []:
        key = f"filing:{filing_id}"
        if key in fired or not imp.measured:
            continue
        events.append((key, sym, imp.kind))
        blocks.append(Line(f"New SEC filing for {sym}: {imp.line()}", "SEC 8-K + prices", "strong"))
    for x in executed or []:
        key = f"paper:{day}:{x.purpose}:{x.symbol}"
        if key in fired:
            continue
        events.append((key, f"{'SOLD' if x.ok else 'COULD NOT SELL'} {x.symbol}", f"{x.purpose}"))
        blocks.insert(0, Line(f"The agent {'sold' if x.ok else 'tried to sell'} {x.amount} of {x.symbol} in the Alpaca paper "
                              f"account: its {x.purpose} rule fired." + ("" if x.ok else f" Alpaca said: {x.detail}"),
                              f"Alpaca paper {now:%H:%M}", "down" if x.purpose == "stop" else "strong"))
    if not events:
        return None, []
    lead_txt = "; ".join(f"{a} ({b})" for _, a, b in events)
    subj = subject_line("urgent", [lead_txt], config.mode == "shadow")
    em = Email("urgent", subj, Line(f"{len(events)} urgent item{'s' if len(events) != 1 else ''}: {lead_txt}.", tone="heading"),
               [Section("Act now" if any(isinstance(b, ActionBox) for b in blocks) else "Heads-up", blocks)],
               Footer(f"{now:%H:%M} ET, {now:%b %d}", None, state.source))
    return em, [k for k, _, _ in events]


# --- Saturday weekly report -----------------------------------------------------------

SECTOR_ETF = {"tech": "XLK", "semiconductors": "XLK", "banks": "XLF", "payments": "XLF", "pharma": "XLV", "health": "XLV",
              "oil": "XLE", "retail": "XLY", "consumer": "XLP", "media": "XLY", "restaurants": "XLY", "apparel": "XLY",
              "railroads": "XLI", "industrials": "XLI", "utilities": "XLU", "materials": "XLB"}
CAUSES = ("calculation", "decision", "system", "expected_variance")


def twr(values: pd.Series, inflows: pd.Series, start: pd.Timestamp, end: pd.Timestamp) -> Optional[float]:
    """Time-weighted return between two closes, with deposits removed."""
    v = values.loc[:end]
    v = v[v.index >= v.index[v.index.searchsorted(start) - 1]] if v.index.searchsorted(start) > 0 else v.loc[start:]
    if len(v) < 2:
        return None
    f = inflows.reindex(v.index, fill_value=0.0)
    daily = ((v - f) / v.shift(1) - 1).iloc[1:]
    daily = daily[v.shift(1).iloc[1:] > 0]
    return float((1 + daily).prod() - 1) if len(daily) else None


def classify(trade, stats: dict[str, dict]) -> tuple[str, str]:
    """(cause, step) for a losing closed trade. A loss within the setup's tested odds is expected variance."""
    ret = trade.exit / trade.entry - 1
    tail = stats.get(trade.setup_id, {}).get("tail_ret")
    step = {"stop": "entry signal (the trade went against it)", "time": "time limit", "signal": "exit rule",
            "target": "target"}.get(trade.reason, trade.reason)
    if tail is not None and ret < tail - 0.001:
        return "decision", step          # worse than 1-in-20 for this setup: the rule, not luck
    return "expected_variance", step


def _decompose(state: AccountState, sym: str, start: pd.Timestamp, end: pd.Timestamp) -> Optional[tuple[float, float, float, float]]:
    from tradeagent.macro import NAMES
    def r(s):
        c = state.bars.get(s, pd.DataFrame()).get("close")
        if c is None:
            return None
        c = c.loc[:end]
        i = c.index.searchsorted(start)
        return None if i == 0 or i > len(c) - 1 else float(c.iloc[-1] / c.iloc[i - 1] - 1)
    total, mkt = r(sym), r("SPY")
    if total is None or mkt is None:
        return None
    sector_etf = SECTOR_ETF.get(NAMES.get(sym, ("", ""))[1])
    sec = r(sector_etf) if sector_etf and sector_etf != sym else None
    sector_part = (sec - mkt) if sec is not None else 0.0
    return total, mkt, sector_part, total - mkt - sector_part


def weekly(state: AccountState, config: Config, *, system_lines: Optional[list[Line]] = None,
           watch_lines: Optional[list[Line]] = None, learning_lines: Optional[list[Line]] = None,
           ideas_lines: Optional[list[Line]] = None) -> Email:
    d = state.sim.daily
    end = state.day
    week_start = end - pd.DateOffset(days=int(end.weekday()))          # Monday of the last session's week
    month_start = end.replace(day=1)
    first = d.index[0]
    lt_in = pd.Series({day: s["long_term"] for day, _, s in state.sim.deposits[1:]}, dtype=float)
    st_in = pd.Series(state.sim.st_inflows, dtype=float).drop(labels=[first], errors="ignore")
    all_in = pd.Series({day: a for day, a, _ in state.sim.deposits[1:]}, dtype=float)
    series = {"Account": (d["value"], all_in), "Long-term": (d["lt_value"] + d["cash_lt"], lt_in),
              "Short-term": (d["st_value"] + d["cash_st"], st_in)}
    bench = pd.DataFrame({b: state.bars[b]["close"] for b in config.goal.benchmark if b in state.bars}).loc[:end]
    bench_val = (bench / bench.iloc[0]).mean(axis=1)
    rows, perf = [], {}
    for name, (vals, flows) in list(series.items()) + [("Index funds", (bench_val, pd.Series(dtype=float)))]:
        cells = []
        for s in (week_start, month_start, first):
            x = twr(vals, flows, max(s, first), end)
            cells.append("–" if x is None else pct(x))
            perf[(name, s)] = x
        rows.append([name, *cells])
    perf_table = Table(["", "Week", "Month", "Since start"], rows, f"{_src(state)} + prices")
    acct_w = perf[("Account", week_start)] or 0.0
    spy = state.bars["SPY"]["close"].loc[:end]
    spy_w = float(spy.iloc[-1] / spy.loc[:week_start - pd.DateOffset(days=1)].iloc[-1] - 1)

    # closed trades this week and the last 4 weeks
    trades = [t for t in state.sim.trades if t.bucket == "short_term"]
    this_week = [t for t in trades if t.exit_day >= week_start]
    last4 = [t for t in trades if t.exit_day >= end - pd.DateOffset(weeks=4)]
    causes4 = [classify(t, state.stats)[0] for t in last4 if t.exit < t.entry]
    from collections import Counter
    counts = Counter(c for c in causes4 if c != "expected_variance")
    fixes = [c for c, n in counts.items() if n >= config.review.recurrence.count]

    well, wrong = [], []
    for t in this_week:
        ret = t.exit / t.entry - 1
        if ret > 0:
            well.append(Line(f"✓ {t.symbol} ({t.setup_id}) {pct(ret)}, closed by its {t.reason}.", f"{_src(state)}", "up"))
        else:
            cause, step = classify(t, state.stats)
            wrong.append(Line(f"✗ {t.symbol} ({t.setup_id}) {pct(ret)}. Cause: {cause.replace('_', ' ')}. Step: {step}.",
                              f"setup {t.setup_id} odds + {_src(state)}", "down"))

    moved = []
    held = {p.symbol for p in state.sim.open_positions} | {t.symbol for t in this_week}
    decomp = [(s, _decompose(state, s, week_start, end)) for s in sorted(held)]
    decomp = sorted([x for x in decomp if x[1]], key=lambda x: -abs(x[1][0]))[:6]
    for s, (tot, m, sec, own) in decomp:
        moved.append(Line(f"{s} {pct(tot)} = market {pct(m)} · sector {pct(sec)} · stock-specific {pct(own)}",
                          "prices (SPY, sector ETF)", "up" if tot >= 0 else "down"))

    score = [[f"{t.setup_id} {t.symbol} {t.entry_day:%b %d}", str(state.stats.get(t.setup_id, {}).get("tier") or "–"),
              "assumed (shadow)", pct(t.exit / t.entry - 1),
              "yes" if classify(t, state.stats)[0] == "expected_variance" or t.exit >= t.entry else "no"]
             for t in this_week]

    nxt_lines = []
    nxt_month = (end + pd.offsets.MonthBegin(1)).normalize()
    if (nxt_month - end).days <= 9 and config.shadow.monthly_deposit > 0:
        lt_share = active_profile(config, ever_reached_switch=d["profile"].iloc[-1] == "moderate").buckets.long_term.target
        dep = config.shadow.monthly_deposit
        nxt_lines.append(Line(f"Deposit expected around {nxt_month:%b %d}: {usd(dep)}, about {usd(dep * lt_share)} long-term "
                              f"/ {usd(dep * (1 - lt_share))} short-term (the 40/60 rule).", "shadow settings"))
    for p in state.sim.open_positions:
        ne = state.next_earnings(p.symbol)
        if ne and 0 < (ne - end.date()).days <= 9:
            nxt_lines.append(Line(f"{p.symbol} reports earnings {ne:%b %d}.", "Yahoo earnings calendar"))

    summary = (f"Account {pct(acct_w)} this week vs SPY {pct(spy_w)}; "
               + ("short-term buys are paused by the goal check." if state.sim.goal_paused else
                  "short-term trading is active."))
    sections = [Section("Performance (time-weighted, deposits removed)", [perf_table])]
    sections.append(Section(f"Fix needed (same cause {config.review.recurrence.count}x in {config.review.recurrence.weeks} weeks)",
                            [Line(f"{c.replace('_', ' ').title()}: {counts[c]} losing trades in 4 weeks traced to this cause. "
                                  f"Proposed change goes to you for approval; nothing changes automatically.",
                                  f"{_src(state)}", "down") for c in fixes]
                            or [Line("None this week.", tone="muted")]))
    sections.append(Section("Why things moved", moved or [Line("No holdings this week.", tone="muted")]))
    sections.append(Section("Recommendation scorecard",
                            [Table(["Recommendation", "Tier", "Acted?", "Result", "Within odds?"], score, _src(state))]
                            if score else [Line("No trades closed this week.", tone="muted")]))
    sections.append(Section("What went well / what went wrong", well + wrong or [Line("Nothing closed this week.", tone="muted")]))
    guards = safeguard_lines(state)
    if guards:
        sections.append(Section("Safeguards", guards))
    if watch_lines:
        sections.append(Section("Watched on paper", watch_lines))
    if learning_lines:
        sections.append(Section("What the paper test is teaching (fixed questions, docs/LEARNING.md)", learning_lines))
    if ideas_lines:
        sections.append(Section("Ideas from GitHub (proposals only: nothing is built until you approve)", ideas_lines))
    if nxt_lines:
        sections.append(Section("Next week", nxt_lines))
    if system_lines:
        sections.append(Section("System", system_lines))
    v = state.value()
    subj = subject_line("weekly", [f"{week_start:%b %d}–{end:%b %d}", usd(v), f"{pct(acct_w)} vs SPY {pct(spy_w)}",
                                   f"{len(fixes)} fix needed" if fixes else "no fix needed"], config.mode == "shadow")
    return Email("weekly", subj, Line(summary, f"{_src(state)} + prices", "strong"), sections, footer(state))
