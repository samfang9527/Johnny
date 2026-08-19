from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime
from typing import Any

from src.domain.training_plan import Workout


class DomainValidationError(ValueError):
    """Raised when activity or health domain data cannot support analytics."""


@dataclass(frozen=True)
class CompletedActivity:
    user_id: str
    source: str
    started_at: datetime
    sport_type: str
    distance_meters: float
    duration_seconds: int
    average_pace_seconds_per_km: float
    source_activity_id: str | None = None
    provider_connection_id: str | None = None
    average_heart_rate: float | None = None
    elevation_gain_meters: float | None = None
    matched_workout_id: str | None = None
    id: str | None = None

    def __post_init__(self) -> None:
        if not self.user_id:
            raise DomainValidationError("user id is required")
        if not self.source:
            raise DomainValidationError("activity source is required")
        if not self.sport_type:
            raise DomainValidationError("sport type is required")
        if self.distance_meters <= 0:
            raise DomainValidationError("activity distance must be greater than zero")
        if self.duration_seconds <= 0:
            raise DomainValidationError("activity duration must be greater than zero")
        if self.average_pace_seconds_per_km <= 0:
            raise DomainValidationError("average pace must be greater than zero")
        if self.average_heart_rate is not None and self.average_heart_rate <= 0:
            raise DomainValidationError("average heart rate must be greater than zero")
        if self.source != "manual":
            if not self.source_activity_id:
                raise DomainValidationError("provider activity requires source activity id")
            if not self.provider_connection_id:
                raise DomainValidationError("provider activity requires provider connection")

    @classmethod
    def create(
        cls,
        *,
        user_id: str,
        source: str,
        started_at: datetime,
        sport_type: str,
        distance_meters: float,
        duration_seconds: int,
        average_pace_seconds_per_km: float | None = None,
        source_activity_id: str | None = None,
        provider_connection_id: str | None = None,
        average_heart_rate: float | None = None,
        elevation_gain_meters: float | None = None,
        matched_workout_id: str | None = None,
        id: str | None = None,
    ) -> CompletedActivity:
        pace = average_pace_seconds_per_km
        if pace is None and distance_meters > 0:
            pace = duration_seconds / (distance_meters / 1000)
        return cls(
            id=id,
            user_id=user_id,
            source=source,
            source_activity_id=source_activity_id,
            provider_connection_id=provider_connection_id,
            started_at=started_at,
            sport_type=sport_type,
            distance_meters=distance_meters,
            duration_seconds=duration_seconds,
            average_pace_seconds_per_km=pace or 0,
            average_heart_rate=average_heart_rate,
            elevation_gain_meters=elevation_gain_meters,
            matched_workout_id=matched_workout_id,
        )

    def with_matched_workout(self, workout_id: str | None) -> CompletedActivity:
        return replace(self, matched_workout_id=workout_id)

    def to_summary(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "average_pace_seconds_per_km": self.average_pace_seconds_per_km,
            "average_heart_rate": self.average_heart_rate,
            "elevation_gain_meters": self.elevation_gain_meters,
            "matched_workout_id": self.matched_workout_id,
        }


@dataclass(frozen=True)
class DailyHealthMetrics:
    user_id: str
    metric_date: date
    source: str = "manual"
    sleep_duration_minutes: float | None = None
    sleep_quality: float | None = None
    hrv_ms: float | None = None
    hrv_baseline_ms: float | None = None
    resting_heart_rate: float | None = None
    stress_score: float | None = None

    def __post_init__(self) -> None:
        if not self.user_id:
            raise DomainValidationError("user id is required")
        if not self.source:
            raise DomainValidationError("health metric source is required")
        _validate_non_negative(self.sleep_duration_minutes, "sleep duration")
        _validate_non_negative(self.sleep_quality, "sleep quality")
        _validate_non_negative(self.hrv_ms, "HRV")
        _validate_non_negative(self.hrv_baseline_ms, "HRV baseline")
        _validate_non_negative(self.resting_heart_rate, "resting heart rate")
        _validate_non_negative(self.stress_score, "stress score")
        if not self.values_by_metric_type():
            raise DomainValidationError("at least one health metric value is required")

    @classmethod
    def create(
        cls,
        *,
        user_id: str,
        metric_date: date,
        source: str = "manual",
        sleep_duration_minutes: float | None = None,
        sleep_quality: float | None = None,
        hrv_ms: float | None = None,
        hrv_baseline_ms: float | None = None,
        resting_heart_rate: float | None = None,
        stress_score: float | None = None,
    ) -> DailyHealthMetrics:
        return cls(
            user_id=user_id,
            metric_date=metric_date,
            source=source,
            sleep_duration_minutes=sleep_duration_minutes,
            sleep_quality=sleep_quality,
            hrv_ms=hrv_ms,
            hrv_baseline_ms=hrv_baseline_ms,
            resting_heart_rate=resting_heart_rate,
            stress_score=stress_score,
        )

    def values_by_metric_type(self) -> dict[str, float]:
        values = {
            "sleep_duration_minutes": self.sleep_duration_minutes,
            "sleep_quality": self.sleep_quality,
            "hrv_ms": self.hrv_ms,
            "hrv_baseline_ms": self.hrv_baseline_ms,
            "resting_heart_rate": self.resting_heart_rate,
            "stress_score": self.stress_score,
        }
        return {metric_type: value for metric_type, value in values.items() if value is not None}


def match_activity_to_workout(activity: CompletedActivity, workouts: tuple[Workout, ...]) -> CompletedActivity:
    candidates = [
        workout
        for workout in workouts
        if workout.id is not None and workout.status == "planned" and workout.scheduled_for == activity.started_at.date()
    ]
    if len(candidates) != 1:
        return activity.with_matched_workout(None)
    return activity.with_matched_workout(candidates[0].id)


def _validate_non_negative(value: float | None, label: str) -> None:
    if value is not None and value < 0:
        raise DomainValidationError(f"{label} cannot be negative")
