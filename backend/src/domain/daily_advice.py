"""Deterministic facts used by Johnny's read-only daily advice."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from src.domain.activity_health import CompletedActivity
from src.domain.training_plan import TrainingPlan, Workout


from src.domain.running import RUNNING_SPORTS, RUNNING_WORKOUT_TYPES
from src.domain.activity_sessions import match_sessions


@dataclass(frozen=True)
class WeekExecution:
    week_start: date
    week_end: date
    status: str
    planned_count: int
    completed_count: int
    missed_count: int
    extra_count: int
    planned_minutes: int | None
    actual_minutes: int
    planned_distance_meters: int | None
    actual_distance_meters: float
    today_completed: bool
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        return {
            "week_start": self.week_start.isoformat(),
            "week_end": self.week_end.isoformat(),
            "status": self.status,
            "planned_count": self.planned_count,
            "completed_count": self.completed_count,
            "missed_count": self.missed_count,
            "extra_count": self.extra_count,
            "planned_minutes": self.planned_minutes,
            "actual_minutes": self.actual_minutes,
            "planned_distance_meters": self.planned_distance_meters,
            "actual_distance_meters": self.actual_distance_meters,
            "today_completed": self.today_completed,
            "evidence": dict(self.evidence),
        }

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> WeekExecution:
        return cls(
            week_start=date.fromisoformat(payload["week_start"]),
            week_end=date.fromisoformat(payload["week_end"]),
            status=payload["status"],
            planned_count=payload["planned_count"],
            completed_count=payload["completed_count"],
            missed_count=payload["missed_count"],
            extra_count=payload["extra_count"],
            planned_minutes=payload["planned_minutes"],
            actual_minutes=payload["actual_minutes"],
            planned_distance_meters=payload["planned_distance_meters"],
            actual_distance_meters=payload["actual_distance_meters"],
            today_completed=payload["today_completed"],
            evidence=dict(payload["evidence"]),
        )


@dataclass(frozen=True, order=True)
class RefreshVersion:
    observed_at: datetime
    run_id: str

    def __post_init__(self) -> None:
        if not self.run_id:
            raise ValueError("refresh run id is required")
        object.__setattr__(self, "observed_at", _as_utc(self.observed_at))


@dataclass(frozen=True)
class WorkoutGuide:
    purpose: str
    expected_feel: str
    if_too_hard: str
    if_too_easy: str

    def to_payload(self) -> dict[str, str]:
        return {
            "purpose": self.purpose,
            "expected_feel": self.expected_feel,
            "if_too_hard": self.if_too_hard,
            "if_too_easy": self.if_too_easy,
        }

    @classmethod
    def from_payload(cls, payload: dict[str, str]) -> WorkoutGuide:
        return cls(**payload)


@dataclass(frozen=True)
class AdviceSections:
    week_summary: str
    today_execution: str
    workout_guide: WorkoutGuide


@dataclass(frozen=True)
class DailyAdvice:
    user_id: str
    advice_date: date
    plan_version_id: str | None
    workout_id: str | None
    week_start: date | None
    week_end: date | None
    execution_mode: str | None
    facts: WeekExecution | None
    sections: AdviceSections | None
    generated_at: datetime | None
    source_sync_run_id: str | None
    source_run_id: str | None
    state: str
    data_freshness: str
    id: str | None = None
    refresh_version: RefreshVersion | None = None
    refresh_source_sync_run_id: str | None = None

    def __post_init__(self) -> None:
        if not self.user_id:
            raise ValueError("daily advice owner is required")
        if self.state not in {"pending", "ready", "sync_failed", "generation_failed", "no_plan"}:
            raise ValueError("daily advice state is invalid")
        if self.data_freshness not in {"fresh", "limited", "stale"}:
            raise ValueError("daily advice freshness is invalid")
        if self.state == "ready" and (self.sections is None or self.facts is None or self.generated_at is None):
            raise ValueError("ready daily advice requires content and generation time")


def plan_week_for_date(plan: TrainingPlan, anchor_date: date) -> tuple[date, date]:
    if not plan.starts_on <= anchor_date <= plan.ends_on:
        raise ValueError("anchor date is outside the training plan")
    block = (anchor_date - plan.starts_on).days // 7
    week_start = date.fromordinal(plan.starts_on.toordinal() + block * 7)
    week_end = min(date.fromordinal(week_start.toordinal() + 6), plan.ends_on)
    return week_start, week_end


def build_week_execution(
    plan: TrainingPlan,
    activities: tuple[CompletedActivity, ...],
    *,
    anchor_date: date,
    as_of: datetime,
    timezone_name: str,
    activity_coverage_complete: bool,
) -> WeekExecution:
    week_start, week_end = plan_week_for_date(plan, anchor_date)
    local_zone = ZoneInfo(timezone_name)
    cutoff = _as_utc(as_of)
    matching_activities = tuple(
        activity
        for activity in activities
        if activity.user_id == plan.user_id
        and activity.sport_type.lower() in RUNNING_SPORTS
        and (started := _as_utc(activity.started_at)) <= cutoff
        and week_start - timedelta(days=1) <= started.astimezone(local_zone).date() <= week_end + timedelta(days=1)
    )
    week_activities = tuple(activity for activity in matching_activities
                            if week_start <= _as_utc(activity.started_at).astimezone(local_zone).date() <= week_end)
    workouts = tuple(
        workout for workout in plan.workouts
        if week_start <= workout.scheduled_for <= week_end and workout.workout_type in RUNNING_WORKOUT_TYPES
    )
    workouts_by_id = {workout.id: workout for workout in workouts if workout.id is not None}
    matched: dict[int, Workout] = {}
    completed_ids: set[int] = set()
    sessions = match_sessions(matching_activities, workouts, timezone_name)
    ambiguous_dates: set[date] = set()
    for session in sessions:
        workout = workouts_by_id.get(session.workout_id)
        if workout is not None:
            for activity in session.activities:
                matched[id(activity)] = workout
            completed_ids.add(id(workout))
        elif session.status == "needs_review":
            ambiguous_dates.update(workout.scheduled_for for workout in session.candidates)

    elapsed = tuple(
        workout for workout in workouts
        if workout.scheduled_for < anchor_date or id(workout) in completed_ids
    )
    missed = tuple(
        workout for workout in workouts
        if workout.scheduled_for < anchor_date
        and id(workout) not in completed_ids
        and workout.scheduled_for not in ambiguous_dates
        and activity_coverage_complete
    )
    extra_sessions = tuple(s for s in sessions if week_start <= s.local_date <= week_end
                           and s.workout_id is None and s.status == "unplanned")
    extra = tuple(activity for session in extra_sessions for activity in session.activities)
    comparable_workouts = tuple(workout for workout in elapsed if workout.planned_duration_minutes is not None)
    planned_minutes = sum(workout.planned_duration_minutes or 0 for workout in comparable_workouts) if comparable_workouts else None
    race_activity_ids = {activity_id for activity_id, workout in matched.items() if workout.workout_type == "race"}
    actual_seconds = sum(
        activity.duration_seconds
        for activity in week_activities if id(activity) not in race_activity_ids
    )
    actual_minutes = actual_seconds // 60
    known_distances = [workout.planned_distance_meters for workout in elapsed if workout.planned_distance_meters is not None]
    planned_distance = sum(known_distances) if known_distances else None
    above = (
        planned_minutes is not None and planned_minutes > 0
        and actual_seconds - planned_minutes * 60 > planned_minutes * 60 * 0.25
        and actual_seconds - planned_minutes * 60 >= 30 * 60
    )
    behind = len(missed) >= 2 or (
        len(missed) >= 1 and planned_minutes is not None and planned_minutes > 0
        and planned_minutes * 60 - actual_seconds >= planned_minutes * 60 * 0.25
        and planned_minutes * 60 - actual_seconds >= 30 * 60
    )
    if ambiguous_dates:
        status = "insufficient_evidence"
    elif above and missed:
        status = "mixed"
    elif above:
        status = "above"
    elif behind:
        status = "behind"
    elif not activity_coverage_complete or planned_minutes is None:
        status = "insufficient_evidence"
    else:
        status = "on_plan"

    return WeekExecution(
        week_start=week_start,
        week_end=week_end,
        status=status,
        planned_count=len(elapsed),
        completed_count=sum(id(workout) in completed_ids for workout in workouts),
        missed_count=len(missed),
        extra_count=len(extra_sessions),
        planned_minutes=planned_minutes,
        actual_minutes=actual_minutes,
        planned_distance_meters=planned_distance,
        actual_distance_meters=sum(activity.distance_meters for activity in week_activities),
        today_completed=any(workout.scheduled_for == anchor_date and id(workout) in completed_ids for workout in workouts),
        evidence={
            "activity_cutoff_at": cutoff.isoformat(),
            "activity_coverage_complete": activity_coverage_complete,
            "ambiguous_dates": [day.isoformat() for day in sorted(ambiguous_dates)],
            "completed_workout_ids": [workout.id for workout in workouts if id(workout) in completed_ids],
            "missed_workout_ids": [workout.id for workout in missed],
            "extra_activity_ids": [activity.id for activity in extra],
            "race_minutes_excluded": bool(race_activity_ids),
        },
    )


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
