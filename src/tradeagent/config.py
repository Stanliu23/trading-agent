"""Load and validate config.yaml (+ config.local.yaml) and pick the active risk profile."""

from __future__ import annotations

from pathlib import Path
from typing import Literal, Optional

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

PROJECT_ROOT = Path(__file__).resolve().parents[2]
_EPS = 1e-9


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


Fraction = Field(ge=0, le=1)


class Band(Strict):
    target: float = Fraction
    min: float = Fraction
    max: float = Fraction

    @model_validator(mode="after")
    def _target_inside_band(self) -> "Band":
        if not (self.min - _EPS <= self.target <= self.max + _EPS):
            raise ValueError(f"target {self.target} is outside its band {self.min}-{self.max}")
        return self


class Buckets(Strict):
    long_term: Band
    short_term: Band

    @model_validator(mode="after")
    def _targets_sum_to_one(self) -> "Buckets":
        total = self.long_term.target + self.short_term.target
        if abs(total - 1) > 1e-6:
            raise ValueError(f"bucket targets must add up to 1, got {total}")
        return self


class Profile(Strict):
    max_loss_per_trade: float = Field(gt=0, le=0.10)
    tier3_max_loss_per_trade: float = Field(gt=0, le=0.10)
    drawdown_pause: float = Field(gt=0, lt=1)
    rank_by: Literal["expected_return", "stars"]
    buckets: Buckets

    @model_validator(mode="after")
    def _tier3_not_larger(self) -> "Profile":
        if self.tier3_max_loss_per_trade > self.max_loss_per_trade + _EPS:
            raise ValueError("tier3_max_loss_per_trade cannot exceed max_loss_per_trade")
        return self


class Profiles(Strict):
    start_profile: Literal["aggressive", "moderate"] = "aggressive"
    switch_to_moderate_at: float = Field(gt=0)
    aggressive: Profile
    moderate: Profile


class Account(Strict):
    broker: str
    reader: Literal["schwab_api", "csv", "undecided"]
    currency: Literal["USD"]
    starting_balance: float = Field(ge=0)
    fractional_shares: bool
    allow_orders: bool
    allow_shorts: bool

    @field_validator("allow_orders")
    @classmethod
    def _never_orders(cls, value: bool) -> bool:
        if value:
            raise ValueError("allow_orders must stay false: this agent never places trades")
        return value


class Universe(Strict):
    markets: list[Literal["us_stocks", "us_etfs"]] = Field(min_length=1)


class Goal(Strict):
    benchmark: list[str] = Field(min_length=1)
    window_sessions: int = Field(ge=20)
    pause_short_term_if_behind: bool
    restart_when_paper_book_recovers: bool = False
    restart_needs_approval: bool = True


class Evidence(Strict):
    min_trades: int = Field(ge=1)
    min_history_years: float = Field(gt=0)
    require_positive_holdout: bool
    min_edge: int = Field(ge=0, le=5)


class Backtest(Strict):
    history_start: str
    end: str
    holdout_start: str
    round_trip_cost: float = Field(ge=0, le=0.02)
    long_term_history_start: str
    long_term_horizon_days: int = Field(ge=20)
    long_term_holdout_years: float = Field(gt=0)

    @model_validator(mode="after")
    def _ordered(self) -> "Backtest":
        if not (self.history_start < self.holdout_start < self.end):
            raise ValueError("need history_start < holdout_start < end")
        if not self.long_term_history_start < self.end:
            raise ValueError("long_term_history_start must be before end")
        return self


def _ascending(values: list[float], name: str) -> list[float]:
    if any(b <= a for a, b in zip(values, values[1:])):
        raise ValueError(f"{name} must be strictly ascending")
    return values


class Scoring(Strict):
    edge_swing_r: list[float] = Field(min_length=5, max_length=5)
    edge_long_term: list[float] = Field(min_length=5, max_length=5)
    confidence_trades: list[int] = Field(min_length=3, max_length=3)
    confidence_years_positive: float = Fraction
    confidence_holdout_decay: float = Fraction
    fit_correlation: list[float] = Field(min_length=5, max_length=5)

    @model_validator(mode="after")
    def _steps_ascending(self) -> "Scoring":
        _ascending(self.edge_swing_r, "edge_swing_r")
        _ascending(self.edge_long_term, "edge_long_term")
        _ascending([float(x) for x in self.confidence_trades], "confidence_trades")
        _ascending(self.fit_correlation, "fit_correlation")
        return self


class Cash(Strict):
    park_idle_in: Optional[str] = None
    min_park_usd: float = Field(ge=0)


class Positions(Strict):
    max_position_pct: float = Field(gt=0, le=1)
    min_position_usd: float = Field(ge=0)
    skip_entries_before_earnings: bool


class TierRule(Strict):
    max_loss_rate: float = Fraction
    max_tail_loss: float = Fraction  # 5th-percentile trade loss


class Tiers(Strict):
    tier1: TierRule
    tier2: TierRule

    @model_validator(mode="after")
    def _tier1_stricter(self) -> "Tiers":
        if (self.tier1.max_loss_rate > self.tier2.max_loss_rate
                or self.tier1.max_tail_loss > self.tier2.max_tail_loss):
            raise ValueError("tier1 limits must be at least as strict as tier2")
        return self


class Stars(Strict):
    components: list[Literal["edge", "confidence", "fit"]] = Field(min_length=1)
    scale: int = Field(ge=1)


class Triggers(Strict):
    move_sigma: float = Field(gt=0)
    urgent_move_sigma: float = Field(gt=0)
    sigma_lookback_days: int = Field(ge=10)
    earnings_within_days: int = Field(ge=0)

    @model_validator(mode="after")
    def _urgent_is_bigger(self) -> "Triggers":
        if self.urgent_move_sigma < self.move_sigma:
            raise ValueError("urgent_move_sigma must be >= move_sigma")
        return self


class MarketData(Strict):
    primary: Literal["yahoo", "finnhub", "schwab"]
    crosscheck: Optional[Literal["yahoo", "finnhub", "schwab"]] = None
    max_disagreement: float = Field(gt=0, le=0.10)

    @model_validator(mode="after")
    def _different_sources(self) -> "MarketData":
        if self.crosscheck == self.primary:
            raise ValueError("crosscheck must be a different source from primary")
        return self


class News(Strict):
    sources: list[Literal["yahoo_finance", "sec_edgar"]] = Field(min_length=1)
    min_similar_events: int = Field(ge=1)


HHMM = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")


class Intraday(Strict):
    every_minutes: int = Field(ge=1, le=120)
    start: str = HHMM
    end: str = HHMM


class Weekly(Strict):
    day: Literal["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    time: str = HHMM


class Schedule(Strict):
    intraday: Intraday
    premarket: str = HHMM
    close: str = HHMM
    weekly: Weekly


class Recurrence(Strict):
    count: int = Field(ge=2)
    weeks: int = Field(ge=1)


class Review(Strict):
    recurrence: Recurrence


class Schwab(Strict):
    login_reminder_day: int = Field(ge=1, le=6)


class EmailLocal(Strict):
    to: Optional[str] = None
    from_: Optional[str] = Field(default=None, alias="from")


class LocalConfig(Strict):
    email: EmailLocal = EmailLocal()


class Config(Strict):
    version: Literal[1]
    mode: Literal["shadow", "live"]
    timezone: str
    account: Account
    universe: Universe
    profiles: Profiles
    goal: Goal
    evidence: Evidence
    backtest: Backtest
    scoring: Scoring
    cash: Cash
    positions: Positions
    tiers: Tiers
    stars: Stars
    triggers: Triggers
    market_data: MarketData
    news: News
    schedule: Schedule
    review: Review
    schwab: Schwab
    local: LocalConfig = LocalConfig()


def _read_yaml(path: Path) -> dict:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a YAML mapping")
    return data


def load_config(root: Path = PROJECT_ROOT) -> Config:
    """Load config.yaml and, if present, config.local.yaml from ``root``."""
    data = _read_yaml(root / "config.yaml")
    local_path = root / "config.local.yaml"
    if local_path.exists():
        data["local"] = _read_yaml(local_path)
    return Config.model_validate(data)


def active_profile_name(config: Config, *, ever_reached_switch: bool) -> Literal["aggressive", "moderate"]:
    """Moderate if the config starts there; otherwise aggressive until the account has once reached the
    switch level, and moderate from then on."""
    if config.profiles.start_profile == "moderate":
        return "moderate"
    return "moderate" if ever_reached_switch else "aggressive"


def reached_switch(config: Config, account_value: float) -> bool:
    return account_value >= config.profiles.switch_to_moderate_at


def active_profile(config: Config, *, ever_reached_switch: bool) -> Profile:
    return getattr(config.profiles, active_profile_name(config, ever_reached_switch=ever_reached_switch))
