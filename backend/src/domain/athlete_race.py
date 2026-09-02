from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import date
from typing import Any


VALID_DAYS = frozenset(
    {
        "monday",
        "tuesday",
        "wednesday",
        "thursday",
        "friday",
        "saturday",
        "sunday",
    }
)
VALID_EXPERIENCE_LEVELS = frozenset({"unknown", "beginner", "intermediate", "advanced"})
VALID_UNIT_PREFERENCES = frozenset({"metric", "imperial"})
VALID_RACE_PRIORITIES = frozenset({"primary", "secondary", "tune_up"})
VALID_RACE_STATUSES = frozenset({"planned", "active", "completed", "cancelled"})


class DomainValidationError(ValueError):
    """Raised when athlete or race domain data cannot support planning."""


@dataclass(frozen=True)
class AthletePreferences:
    preferred_training_days: tuple[str, ...]
    preferred_long_run_day: str
    max_runs_per_week: int
    unit_preference: str = "metric"
    training_preferences: dict[str, Any] = field(default_factory=dict)
    injury_notes: str | None = None

    def __post_init__(self) -> None:
        normalized_days = tuple(_normalize_day(day) for day in self.preferred_training_days)
        if len(set(normalized_days)) != len(normalized_days):
            raise DomainValidationError("preferred training days must be unique")
        normalized_long_run_day = _normalize_day(self.preferred_long_run_day)
        if self.max_runs_per_week < 1 or self.max_runs_per_week > 7:
            raise DomainValidationError("maximum runs per week must be between 1 and 7")
        if self.max_runs_per_week < len(normalized_days):
            raise DomainValidationError("maximum runs per week must cover preferred training days")
        if self.unit_preference not in VALID_UNIT_PREFERENCES:
            raise DomainValidationError("unit preference must be metric or imperial")

        object.__setattr__(self, "preferred_training_days", normalized_days)
        object.__setattr__(self, "preferred_long_run_day", normalized_long_run_day)
        object.__setattr__(self, "training_preferences", dict(self.training_preferences))


@dataclass(frozen=True)
class AthleteProfile:
    user_id: str
    timezone: str
    experience_level: str
    current_weekly_mileage: float
    preferences: AthletePreferences
    id: str | None = None

    def __post_init__(self) -> None:
        if not self.user_id:
            raise DomainValidationError("user id is required")
        if not self.timezone:
            raise DomainValidationError("timezone is required")
        if self.experience_level not in VALID_EXPERIENCE_LEVELS:
            raise DomainValidationError("experience level is invalid")
        if self.current_weekly_mileage < 0:
            raise DomainValidationError("current weekly mileage cannot be negative")

    @classmethod
    def create(
        cls,
        *,
        user_id: str,
        timezone: str,
        experience_level: str,
        current_weekly_mileage: float,
        preferred_training_days: tuple[str, ...],
        preferred_long_run_day: str,
        max_runs_per_week: int,
        unit_preference: str = "metric",
        training_preferences: dict[str, Any] | None = None,
        injury_notes: str | None = None,
        id: str | None = None,
    ) -> AthleteProfile:
        return cls(
            id=id,
            user_id=user_id,
            timezone=timezone,
            experience_level=experience_level,
            current_weekly_mileage=current_weekly_mileage,
            preferences=AthletePreferences(
                preferred_training_days=preferred_training_days,
                preferred_long_run_day=preferred_long_run_day,
                max_runs_per_week=max_runs_per_week,
                unit_preference=unit_preference,
                training_preferences=training_preferences or {},
                injury_notes=injury_notes,
            ),
        )

    def with_preferences(self, preferences: AthletePreferences) -> AthleteProfile:
        return replace(self, preferences=preferences)


@dataclass(frozen=True)
class RaceGoal:
    user_id: str
    name: str
    race_date: date
    distance_meters: int
    target_finish_seconds: int | None = None
    priority: str = "primary"
    status: str = "planned"
    id: str | None = None

    def __post_init__(self) -> None:
        if not self.user_id:
            raise DomainValidationError("user id is required")
        if not self.name:
            raise DomainValidationError("race name is required")
        if self.distance_meters <= 0:
            raise DomainValidationError("race distance must be greater than zero")
        if self.target_finish_seconds is not None and self.target_finish_seconds <= 0:
            raise DomainValidationError("target finish time must be greater than zero")
        if self.priority not in VALID_RACE_PRIORITIES:
            raise DomainValidationError("race priority is invalid")
        if self.status not in VALID_RACE_STATUSES:
            raise DomainValidationError("race status is invalid")

    @classmethod
    def create(
        cls,
        *,
        user_id: str,
        name: str,
        race_date: date,
        distance_meters: int,
        target_finish_seconds: int | None = None,
        priority: str = "primary",
        status: str = "planned",
        id: str | None = None,
    ) -> RaceGoal:
        return cls(
            id=id,
            user_id=user_id,
            name=name,
            race_date=race_date,
            distance_meters=distance_meters,
            target_finish_seconds=target_finish_seconds,
            priority=priority,
            status=status,
        )

    @property
    def target_pace_seconds_per_km(self) -> float | None:
        if self.target_finish_seconds is None:
            return None
        return self.target_finish_seconds / (self.distance_meters / 1000)


def validate_race_goal_date(race_goal: RaceGoal, *, as_of: date) -> None:
    if race_goal.race_date < as_of:
        raise DomainValidationError("race date cannot be in the past")


def _normalize_day(day: str) -> str:
    normalized_day = day.strip().lower()
    if normalized_day not in VALID_DAYS:
        raise DomainValidationError(f"invalid training day: {day}")
    return normalized_day
