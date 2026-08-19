from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import date
from typing import Any


SUPPORTED_WORKOUT_TYPES = frozenset(
    {
        "easy_run",
        "long_run",
        "tempo",
        "interval",
        "recovery",
        "rest",
        "strength",
        "cross_training",
    }
)
VALID_PLAN_STATUSES = frozenset({"active", "completed", "archived"})
VALID_WORKOUT_STATUSES = frozenset({"planned", "adjusted", "completed", "skipped"})
WORKOUT_STATUS_TRANSITIONS = {
    "planned": frozenset({"adjusted", "completed", "skipped"}),
    "adjusted": frozenset({"completed", "skipped"}),
    "completed": frozenset(),
    "skipped": frozenset(),
}
VALID_PROPOSAL_STATUSES = frozenset({"proposed", "approved", "rejected", "applied"})
PROPOSAL_STATUS_TRANSITIONS = {
    "proposed": frozenset({"approved", "rejected"}),
    "approved": frozenset({"applied"}),
    "rejected": frozenset(),
    "applied": frozenset(),
}


class DomainValidationError(ValueError):
    """Raised when training plan domain data cannot support planning."""


@dataclass(frozen=True)
class Workout:
    scheduled_for: date
    workout_type: str
    purpose: str
    planned_duration_minutes: int | None = None
    planned_distance_meters: int | None = None
    pace_range_seconds_per_km: tuple[int, int] | None = None
    heart_rate_zone: str | None = None
    status: str = "planned"
    id: str | None = None

    def __post_init__(self) -> None:
        if self.workout_type not in SUPPORTED_WORKOUT_TYPES:
            raise DomainValidationError("workout type is not supported")
        if not self.purpose:
            raise DomainValidationError("workout purpose is required")
        if self.status not in VALID_WORKOUT_STATUSES:
            raise DomainValidationError("workout status is invalid")
        if self.planned_duration_minutes is None and self.planned_distance_meters is None:
            raise DomainValidationError("workout requires planned distance or duration")
        if self.planned_duration_minutes is not None and self.planned_duration_minutes <= 0:
            raise DomainValidationError("planned duration must be greater than zero")
        if self.planned_distance_meters is not None and self.planned_distance_meters <= 0:
            raise DomainValidationError("planned distance must be greater than zero")
        if self.pace_range_seconds_per_km is not None:
            lower, upper = self.pace_range_seconds_per_km
            if lower <= 0 or upper <= 0 or lower > upper:
                raise DomainValidationError("pace range is invalid")

    @classmethod
    def create(
        cls,
        *,
        scheduled_for: date,
        workout_type: str,
        purpose: str,
        planned_duration_minutes: int | None = None,
        planned_distance_meters: int | None = None,
        pace_range_seconds_per_km: tuple[int, int] | None = None,
        heart_rate_zone: str | None = None,
        status: str = "planned",
        id: str | None = None,
    ) -> Workout:
        return cls(
            id=id,
            scheduled_for=scheduled_for,
            workout_type=workout_type,
            purpose=purpose,
            planned_duration_minutes=planned_duration_minutes,
            planned_distance_meters=planned_distance_meters,
            pace_range_seconds_per_km=pace_range_seconds_per_km,
            heart_rate_zone=heart_rate_zone,
            status=status,
        )

    def transition_to(self, status: str) -> Workout:
        if status not in WORKOUT_STATUS_TRANSITIONS[self.status]:
            raise DomainValidationError(f"invalid workout status transition: {self.status} -> {status}")
        return replace(self, status=status)

    def to_payload(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "scheduled_for": self.scheduled_for.isoformat(),
            "workout_type": self.workout_type,
            "purpose": self.purpose,
            "planned_duration_minutes": self.planned_duration_minutes,
            "planned_distance_meters": self.planned_distance_meters,
            "pace_range_seconds_per_km": list(self.pace_range_seconds_per_km)
            if self.pace_range_seconds_per_km is not None
            else None,
            "heart_rate_zone": self.heart_rate_zone,
            "status": self.status,
        }


@dataclass(frozen=True)
class TrainingPlan:
    user_id: str
    name: str
    starts_on: date
    ends_on: date
    race_id: str | None = None
    status: str = "active"
    workouts: tuple[Workout, ...] = field(default_factory=tuple)
    id: str | None = None

    def __post_init__(self) -> None:
        if not self.user_id:
            raise DomainValidationError("user id is required")
        if not self.name:
            raise DomainValidationError("training plan name is required")
        if self.status not in VALID_PLAN_STATUSES:
            raise DomainValidationError("training plan status is invalid")
        if self.ends_on < self.starts_on:
            raise DomainValidationError("training plan end date cannot be before start date")
        ordered_workouts = tuple(sorted(self.workouts, key=lambda workout: workout.scheduled_for))
        for workout in ordered_workouts:
            if workout.scheduled_for < self.starts_on or workout.scheduled_for > self.ends_on:
                raise DomainValidationError("workout is outside plan date range")
        object.__setattr__(self, "workouts", ordered_workouts)

    @classmethod
    def create(
        cls,
        *,
        user_id: str,
        name: str,
        starts_on: date,
        ends_on: date,
        race_id: str | None = None,
        status: str = "active",
        workouts: tuple[Workout, ...] = (),
        id: str | None = None,
    ) -> TrainingPlan:
        return cls(
            id=id,
            user_id=user_id,
            race_id=race_id,
            name=name,
            status=status,
            starts_on=starts_on,
            ends_on=ends_on,
            workouts=workouts,
        )


@dataclass(frozen=True)
class PlanAdjustmentProposal:
    user_id: str
    training_plan_id: str
    before_payload: dict[str, Any]
    after_payload: dict[str, Any]
    workout_id: str | None = None
    recommendation_id: str | None = None
    status: str = "proposed"
    id: str | None = None

    def __post_init__(self) -> None:
        if not self.user_id:
            raise DomainValidationError("user id is required")
        if not self.training_plan_id:
            raise DomainValidationError("training plan id is required")
        if not self.before_payload:
            raise DomainValidationError("before payload is required")
        if not self.after_payload:
            raise DomainValidationError("after payload is required")
        if self.status not in VALID_PROPOSAL_STATUSES:
            raise DomainValidationError("proposal status is invalid")
        object.__setattr__(self, "before_payload", dict(self.before_payload))
        object.__setattr__(self, "after_payload", dict(self.after_payload))

    @classmethod
    def create(
        cls,
        *,
        user_id: str,
        training_plan_id: str,
        before_payload: dict[str, Any],
        after_payload: dict[str, Any],
        workout_id: str | None = None,
        recommendation_id: str | None = None,
        status: str = "proposed",
        id: str | None = None,
    ) -> PlanAdjustmentProposal:
        return cls(
            id=id,
            user_id=user_id,
            training_plan_id=training_plan_id,
            workout_id=workout_id,
            recommendation_id=recommendation_id,
            before_payload=before_payload,
            after_payload=after_payload,
            status=status,
        )

    def transition_to(self, status: str) -> PlanAdjustmentProposal:
        if status not in PROPOSAL_STATUS_TRANSITIONS[self.status]:
            raise DomainValidationError(f"invalid proposal status transition: {self.status} -> {status}")
        return replace(self, status=status)
