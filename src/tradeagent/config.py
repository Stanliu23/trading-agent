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


class Evidence(Strict):
    min_trades: int = Field(ge=1)
    min_history_years: float = Field(gt=0)
    require_positive_holdout: bool


class TierRule(Strict):
    max_loss_rate: float = Fraction
    max_worst_drop: float = Fraction


class Tiers(Strict):
    tier1: TierRule
    tier2: TierRule

    @model_validator(mode="after")
    def _tier1_stricter(self) -> "Tiers":
        if (self.tier1.max_loss_rate > self.tier2.max_loss_rate
                or self.tier1.max_worst_drop > self.tier2.max_worst_drop):
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
    evidence: Evidence
    tiers: Tiers
    stars: Stars
    triggers: Triggers
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
    """Aggressive until the account has once reached the switch level; moderate from then on."""
    return "moderate" if ever_reached_switch else "aggressive"


def reached_switch(config: Config, account_value: float) -> bool:
    return account_value >= config.profiles.switch_to_moderate_at


def active_profile(config: Config, *, ever_reached_switch: bool) -> Profile:
    return getattr(config.profiles, active_profile_name(config, ever_reached_switch=ever_reached_switch))
