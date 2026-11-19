"""Turn a setup's trades into the numbers that decide its tier and scores."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Optional

import pandas as pd

from tradeagent.config import Config
from tradeagent.setups.library import Setup
from tradeagent.setups.simulate import Trade


@dataclass(frozen=True)
class SetupStats:
    setup_id: str
    name: str
    bucket: str
    kind: str
    symbols_tested: int
    n: int
    first_entry: Optional[str]
    loss_rate: Optional[float]
    mean_ret: Optional[float]
    median_ret: Optional[float]
    tail_ret: Optional[float]            # 5th-percentile trade: 1 in 20 did worse
    worst_ret: Optional[float]
    best_ret: Optional[float]
    exp_r: Optional[float]               # swing only: mean R after costs
    stop_rate: Optional[float]
    avg_hold_days: Optional[float]
    years_positive: Optional[float]
    holdout_start: Optional[str]
    in_n: int
    in_metric: Optional[float]           # exp_r (swing) or mean_ret (accumulate), before holdout_start
    out_n: int
    out_metric: Optional[float]          # same metric on the held-out period
    passes_evidence: bool
    evidence_note: str
    tier: Optional[int]
    edge: int
    confidence: int

    def as_dict(self) -> dict:
        return asdict(self)


def _metric(frame: pd.DataFrame, kind: str) -> Optional[float]:
    if frame.empty:
        return None
    return float(frame["r"].mean() if kind == "swing" else frame["ret"].mean())


def _steps(value: Optional[float], steps: list[float]) -> int:
    if value is None:
        return 0
    return sum(value > s for s in steps)


def tier_for(loss_rate: float, tail_ret: float, config: Config) -> int:
    """Tier from loss rate and the 5th-percentile trade (not the single worst trade)."""
    t1, t2 = config.tiers.tier1, config.tiers.tier2
    if loss_rate <= t1.max_loss_rate and tail_ret >= -t1.max_tail_loss:
        return 1
    if loss_rate <= t2.max_loss_rate and tail_ret >= -t2.max_tail_loss:
        return 2
    return 3


def compute_stats(setup: Setup, trades: list[Trade], symbols_tested: int, config: Config,
                  holdout: Optional[pd.Timestamp] = None) -> SetupStats:
    """Stats for one setup. ``holdout`` defaults to backtest.holdout_start for swing setups and to the
    last ``long_term_holdout_years`` of entry dates for accumulate setups."""
    ev, sc, bt = config.evidence, config.scoring, config.backtest
    if not trades:
        return SetupStats(setup.id, setup.name, setup.bucket, setup.kind, symbols_tested, 0, None, None, None,
                          None, None, None, None, None, None, None, None, None, 0, None, 0, None, False,
                          "no trades", None, 0, 0)

    df = pd.DataFrame([t.__dict__ for t in trades])
    kind = setup.kind
    if holdout is None:
        if kind == "swing":
            holdout = pd.Timestamp(bt.holdout_start)
        else:
            holdout = df["entry_date"].max() - pd.DateOffset(days=round(365.25 * bt.long_term_holdout_years))
    ins, out = df[df["entry_date"] < holdout], df[df["entry_date"] >= holdout]
    in_m, out_m = _metric(ins, kind), _metric(out, kind)
    by_year = df.groupby(df["entry_date"].dt.year)["ret"].mean()
    years_positive = float((by_year > 0).mean())
    span_years = (df["entry_date"].max() - df["entry_date"].min()).days / 365.25

    problems = []
    if len(df) < ev.min_trades:
        problems.append(f"only {len(df)} trades (need {ev.min_trades})")
    if span_years < ev.min_history_years - 0.5:
        problems.append(f"only {span_years:.1f} years of history")
    if ev.require_positive_holdout and not (out_m is not None and out_m > 0):
        problems.append("held-out result not positive" if out_m is not None else "no held-out trades")
    passes = not problems

    loss_rate = float((df["ret"] <= 0).mean())
    tail = float(df["ret"].quantile(0.05))
    worst = float(df["ret"].min())

    steps = sc.edge_swing_r if kind == "swing" else sc.edge_long_term
    edge = _steps(out_m, steps) if passes else 0

    confidence = 0
    if passes:
        confidence = 2 + sum(len(df) >= t for t in sc.confidence_trades[1:])
        if years_positive >= sc.confidence_years_positive:
            confidence += 1
        if in_m is not None and in_m > 0 and out_m is not None and out_m < sc.confidence_holdout_decay * in_m:
            confidence -= 1
        if kind == "accumulate":
            confidence = min(confidence, 2)  # overlapping 12-month windows are not independent
        confidence = max(0, min(5, confidence))

    return SetupStats(
        setup_id=setup.id, name=setup.name, bucket=setup.bucket, kind=kind, symbols_tested=symbols_tested,
        n=len(df), first_entry=str(df["entry_date"].min().date()),
        loss_rate=loss_rate, mean_ret=float(df["ret"].mean()), median_ret=float(df["ret"].median()),
        tail_ret=tail, worst_ret=worst, best_ret=float(df["ret"].max()),
        exp_r=float(df["r"].mean()) if kind == "swing" else None,
        stop_rate=float((df["reason"] == "stop").mean()) if kind == "swing" else None,
        avg_hold_days=float(df["hold_days"].mean()), years_positive=years_positive,
        holdout_start=str(holdout.date()), in_n=len(ins), in_metric=in_m, out_n=len(out), out_metric=out_m,
        passes_evidence=passes, evidence_note="; ".join(problems) or "passes",
        tier=tier_for(loss_rate, tail, config) if passes else None,
        edge=edge, confidence=confidence,
    )


def stars(edge: int, confidence: int, fit: int) -> int:
    """Average of the three 0-5 sub-scores, rounded half up."""
    for v in (edge, confidence, fit):
        if not 0 <= v <= 5:
            raise ValueError("sub-scores must be 0-5")
    return int(math.floor((edge + confidence + fit) / 3 + 0.5))
