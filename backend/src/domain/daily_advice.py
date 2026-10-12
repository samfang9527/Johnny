"""Deterministic facts used by Johnny's read-only daily advice."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

from src.domain.activity_health import CompletedActivity
from src.domain.training_plan import TrainingPlan, Workout


RUNNING_SPORTS = frozenset({"run", "running", "trail_run", "trail_running", "virtual_run", "treadmill_run"})
RUNNING_WORKOUT_TYPES = frozenset({"easy_run", "long_run", "tempo", "interval", "hill", "recovery", "race"})


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
    week_activities = tuple(
        activity
        for activity in activities
        if activity.user_id == plan.user_id
        and activity.sport_type.lower() in RUNNING_SPORTS
        and (started := _as_utc(activity.started_at)) <= cutoff
        and week_start <= started.astimezone(local_zone).date() <= week_end
    )
    local_dates = {id(activity): _as_utc(activity.started_at).astimezone(local_zone).date() for activity in week_activities}
    workouts = tuple(
        workout for workout in plan.workouts
        if week_start <= workout.scheduled_for <= week_end and workout.workout_type in RUNNING_WORKOUT_TYPES
    )
    workouts_by_id = {workout.id: workout for workout in workouts if workout.id is not None}
    matched: dict[int, Workout] = {}
    completed_ids: set[int] = set()
    for activity in week_activities:
        workout = workouts_by_id.get(activity.matched_workout_id)
        if workout is not None:
            matched[id(activity)] = workout
            completed_ids.add(id(workout))

    ambiguous_dates: set[date] = set()
    for day in sorted({workout.scheduled_for for workout in workouts} | set(local_dates.values())):
        pending_workouts = [
            workout for workout in workouts
            if workout.scheduled_for == day and id(workout) not in completed_ids
        ]
        pending_activities = [
            activity for activity in week_activities
            if local_dates[id(activity)] == day and id(activity) not in matched
        ]
        if len(pending_workouts) == len(pending_activities) == 1:
            workout, activity = pending_workouts[0], pending_activities[0]
            matched[id(activity)] = workout
            completed_ids.add(id(workout))
        elif pending_workouts and pending_activities:
            ambiguous_dates.add(day)

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
    extra = tuple(
        activity for activity in week_activities
        if id(activity) not in matched and local_dates[id(activity)] not in ambiguous_dates
    )
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
        extra_count=len(extra),
        planned_minutes=planned_minutes,
        actual_minutes=actual_minutes,
        planned_distance_meters=planned_distance,
        actual_distance_meters=sum(activity.distance_meters for activity in week_activities),
        today_completed=any(workout.scheduled_for == anchor_date and id(workout) in completed_ids for workout in workouts),
        evidence={
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
