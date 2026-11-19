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
    return f"shadow account {state.day:%m-%d}"


def footer(state: AccountState) -> Footer:
    return Footer(f"close {state.day:%b %d}", None, "hypothetical account")


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
    v, prev = state.value(), float(daily["value"].iloc[-2]) if len(daily) > 1 else state.value()
    dep_today = sum(a for d, a, _ in state.sim.deposits if d == state.day)
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
             Line(f"Cash parked in {config.cash.park_idle_in or 'cash'} {usd(cash)} · drop from peak {pct(dd)} "
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
    prev = float(state.sim.daily["value"].iloc[-2]) if len(state.sim.daily) > 1 else v
    dep_today = sum(a for d, a, _ in state.sim.deposits if d == state.day)
    ch = v - prev - dep_today
    spy = state.bars["SPY"]["close"].loc[:state.day]
    subj = subject_line("digest", [f"{state.day:%a %b %d}", usd(v), f"{usd(ch, True)} ({pct(ch / prev if prev else 0)})",
                                   f"SPY {pct(float(spy.iloc[-1] / spy.iloc[-2] - 1))}",
                                   f"{n_actions} action{'s' if n_actions != 1 else ''}"], config.mode == "shadow")
    return Email("digest", subj, lead, sections, footer(state))
