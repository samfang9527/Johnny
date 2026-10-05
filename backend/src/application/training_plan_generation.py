from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, timedelta
from math import ceil
from typing import Any, Mapping, Sequence
from uuid import uuid4

from src.domain.training_plan import (
    HARD_SESSION_WORKOUT_TYPES,
    DomainValidationError,
    SUPPORTED_PLAN_PHASES,
    TrainingPlan,
    Workout,
    WorkoutStep,
    WorkoutTarget,
    validate_phase_segments,
    workout_purpose_zh,
)
from src.domain.training_plan_regeneration import (
    RaceStrategySelection,
    projection_window,
    select_race_strategy,
)
from src.application.training_workload_policy import (
    CapacitySnapshot, RaceDemand, WorkloadPrescription, assess_preparation,
    build_workload_prescription, derive_capacity_snapshot,
)


DEFAULT_TRAINING_DAYS = ("tuesday", "thursday", "sunday")
DAY_INDEX = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}
QUALITY_WORKOUT_TYPES = ("interval", "tempo", "hill")


@dataclass(frozen=True)
class PlanRace:
    race_goal_id: str
    name: str
    race_date: date
    distance_meters: int
    priority: str
    is_target: bool
    goal_intent: str | None


@dataclass(frozen=True)
class SkeletonWorkout:
    scheduled_for: date
    workout_type: str
    phase: str
    planned_duration_minutes: int | None
    planned_distance_meters: int | None
    race_goal_id: str | None = None
    race_name: str | None = None
    race_priority: str | None = None
    focus_zone: str | None = None
    race_goal_intent: str | None = None
    is_target_race: bool = False


@dataclass(frozen=True)
class PlanSkeleton:
    starts_on: date
    ends_on: date
    phase_segments: list[dict]
    workouts: list[SkeletonWorkout]
    workload_prescription: WorkloadPrescription | None = None


@dataclass(frozen=True)
class CompletionRepairResult:
    plan: TrainingPlan
    repaired_week_indexes: list[int]
    repaired_workout_ids: list[str]
    reason: str | None


def effective_hard_session_limit(
    max_runs_per_week: int,
    max_hard_sessions_per_week: int = 2,
    injury_status: str = "none",
) -> int:
    if max_hard_sessions_per_week < 0 or max_hard_sessions_per_week > 2:
        raise ValueError("maximum hard sessions per week must be between 0 and 2")
    limit = min(max_hard_sessions_per_week, ceil(max_runs_per_week / 2), 2)
    if injury_status in {"current", "recent"}:
        limit = min(limit, 1)
    return limit


def build_plan_skeleton(
    *,
    starts_on: date,
    ends_on: date,
    plan_type: str,
    race_date: date | None,
    preferred_training_days: Sequence[str],
    preferred_long_run_day: str,
    max_runs_per_week: int,
    max_hard_sessions_per_week: int = 2,
    injury_status: str = "none",
    race_distance_meters: int | None = None,
    current_weekly_mileage_km: float | None = None,
    experience_level: str | None = None,
    capacity_snapshot: CapacitySnapshot | None = None,
    race_demand: RaceDemand | None = None,
    prior_plan: Mapping[str, Any] | None = None,
    races: Sequence[PlanRace] = (),
) -> PlanSkeleton:
    if ends_on < starts_on:
        raise ValueError("plan end date cannot be before start date")
    if plan_type not in {"maintenance", "race"}:
        raise ValueError(f"unsupported plan type: {plan_type}")

    phase_segments = _build_phase_segments(starts_on, ends_on, plan_type, race_date, race_distance_meters)
    capacity = capacity_snapshot or derive_capacity_snapshot(
        profile={"current_weekly_mileage_km": current_weekly_mileage_km}, activities=(), anchor=starts_on,
    )
    demand = race_demand or (
        RaceDemand(race_distance_meters, race_date, None, None, None, None, None, None)
        if race_date is not None and race_distance_meters is not None else None
    )
    prescription = build_workload_prescription(
        capacity=capacity, race=demand, starts_on=starts_on, ends_on=ends_on,
        phase_segments=phase_segments, max_runs_per_week=max_runs_per_week,
        max_hard_sessions_per_week=max_hard_sessions_per_week,
        injury_status=injury_status, prior_plan=prior_plan,
    )
    phase_by_day = _phase_by_day(phase_segments)
    training_days = tuple(preferred_training_days) or DEFAULT_TRAINING_DAYS
    selected_days = _selected_training_days(training_days, preferred_long_run_day, max_runs_per_week)
    hard_session_limit = effective_hard_session_limit(
        max_runs_per_week,
        max_hard_sessions_per_week,
        injury_status,
    )
    effective_mileage = capacity.weekly_distance_km or current_weekly_mileage_km
    known_mileage = effective_mileage is not None and effective_mileage > 0
    quality_allowed = (
        known_mileage and injury_status == "none"
        and (
            (effective_mileage >= 20 and experience_level in {"intermediate", "advanced"})
            or (effective_mileage >= 40 and experience_level == "beginner")
        )
    )
    aerobic_only = plan_type == "race" and (race_date is None or race_date > ends_on)
    if not quality_allowed or aerobic_only:
        hard_session_limit = min(hard_session_limit, 1)

    weeks = [
        (
            week_start,
            _scheduled_days(week_start, selected_days, ends_on, max_runs_per_week),
        )
        for week_start in _week_starts(starts_on, ends_on)
    ]
    preferred_long_run_dates = [
        scheduled_for
        for _, scheduled_days in weeks
        for scheduled_for in scheduled_days
        if len(scheduled_days) > 1 and hard_session_limit > 0 and scheduled_for.weekday() == DAY_INDEX[preferred_long_run_day]
    ]

    workouts: list[SkeletonWorkout] = []
    hard_dates = list(preferred_long_run_dates)
    quality_index = 0
    for week_index, (_, scheduled_days) in enumerate(weeks):
        long_run_day = next((day for day in scheduled_days if day in preferred_long_run_dates), None)
        workout_type_by_date = {long_run_day: "long_run"} if long_run_day is not None else {}
        weekly_hard_session_count = int(long_run_day is not None)

        for scheduled_for in scheduled_days:
            if not quality_allowed or aerobic_only:
                continue
            if scheduled_for == long_run_day or weekly_hard_session_count >= hard_session_limit:
                continue
            if not _is_safely_spaced(scheduled_for, hard_dates):
                continue
            phase = phase_by_day[scheduled_for]
            if phase in {"taper", "race"}:
                continue
            if phase == "base" and plan_type == "race" and week_index % 2:
                continue
            quality_types = _quality_types_for_phase(
                phase, race_distance_meters, terrain_focus=prescription.weeks[week_index].terrain_focus,
            )
            workout_type_by_date[scheduled_for] = quality_types[quality_index % len(quality_types)]
            quality_index += 1
            weekly_hard_session_count += 1
            hard_dates.append(scheduled_for)

        for scheduled_for in scheduled_days:
            workout_type = workout_type_by_date.get(scheduled_for, "easy_run")
            workouts.append(
                SkeletonWorkout(
                    scheduled_for=scheduled_for,
                    workout_type=workout_type,
                    phase=phase_by_day[scheduled_for],
                    planned_duration_minutes=0,
                    planned_distance_meters=None,
                    focus_zone=_focus_zone_for_workout(workout_type, phase_by_day[scheduled_for], race_distance_meters),
                )
            )

    # Allocate the complete weekly budget to its scheduled workouts, preserving
    # the policy long-run cap and exact weekly totals.
    allocated: list[SkeletonWorkout] = []
    weekly_totals: list[int] = []
    weekly_longs: list[int] = []
    for week_index, (_, scheduled_days) in enumerate(weeks):
        week_workouts = [workout for workout in workouts if workout.scheduled_for in scheduled_days]
        if not week_workouts:
            weekly_totals.append(0)
            weekly_longs.append(0)
            continue
        # One available run cannot safely carry a full week's training volume.
        budget = min(prescription.weeks[week_index].target_minutes, 90) if len(week_workouts) == 1 else prescription.weeks[week_index].target_minutes
        long_workout = next((workout for workout in week_workouts if workout.workout_type == "long_run"), None)
        long_minutes = min(prescription.weeks[week_index].long_run_minutes, max(1, budget - len(week_workouts) + 1)) if long_workout else 0
        ordinary_count = len(week_workouts) - int(long_workout is not None)
        ordinary_budget = budget - long_minutes
        each, extra = divmod(ordinary_budget, ordinary_count) if ordinary_count else (0, 0)
        ordinary_index = 0
        for workout in week_workouts:
            if workout is long_workout:
                duration = long_minutes
            else:
                duration = each + int(ordinary_index < extra)
                ordinary_index += 1
            allocated.append(replace(workout, planned_duration_minutes=duration))
        weekly_totals.append(sum(workout.planned_duration_minutes or 0 for workout in allocated if workout.scheduled_for in scheduled_days))
        weekly_longs.append(long_minutes)
    allocated, race_schedule_constrained, race_conflict = _reserve_race_workouts(
        allocated, races, starts_on=starts_on, ends_on=ends_on, max_runs_per_week=max_runs_per_week,
        phase_by_day=phase_by_day,
    )
    allocated, hard_session_conflict = _adjust_training_around_races(
        allocated, starts_on=starts_on, prescription=prescription,
        max_runs_per_week=max_runs_per_week, hard_session_limit=hard_session_limit,
    )
    weekly_totals = [
        sum(workout.planned_duration_minutes or 0 for workout in allocated if week_start <= workout.scheduled_for <= min(week_start + timedelta(days=6), ends_on))
        for week_start in _week_starts(starts_on, ends_on)
    ]
    weekly_longs = [
        sum(workout.planned_duration_minutes or 0 for workout in allocated if workout.workout_type == "long_run" and week_start <= workout.scheduled_for <= min(week_start + timedelta(days=6), ends_on))
        for week_start in _week_starts(starts_on, ends_on)
    ]
    development_indexes = [week.week_index for week in prescription.weeks if week.phase not in {"taper", "race"}]
    final_development_indexes = set(development_indexes[-8:])
    actual_assessment = assess_preparation(
        capacity=capacity, race=demand, starts_on=starts_on, ends_on=ends_on,
        weekly_minutes=[total for total, week in zip(weekly_totals, prescription.weeks) if week.phase not in {"taper", "race"}],
        long_run_minutes=[minutes for minutes, week in zip(weekly_longs, prescription.weeks) if week.phase not in {"taper", "race"}],
        terrain_session_count=sum(
            workout.workout_type == "hill"
            and (workout.scheduled_for - starts_on).days // 7 in final_development_indexes
            for workout in allocated
        ),
        policy_version=prescription.policy_version,
    )
    extra_factors = []
    if race_schedule_constrained:
        extra_factors.append("constrained_schedule")
    if race_conflict:
        extra_factors.append("race_conflict")
    if hard_session_conflict:
        extra_factors.append("hard_session_capacity")
    if extra_factors:
        actual_assessment = replace(
            actual_assessment,
            factors=(*actual_assessment.factors, *extra_factors),
            explanation_zh=f"{actual_assessment.explanation_zh}；賽事日期限制了可安排的訓練日",
        )
    actual_weeks = tuple(
        replace(week, target_minutes=weekly_totals[index], long_run_minutes=weekly_longs[index])
        for index, week in enumerate(prescription.weeks)
    )
    prescription = WorkloadPrescription(actual_weeks, actual_assessment, prescription.policy_version)
    return PlanSkeleton(
        starts_on=starts_on,
        ends_on=ends_on,
        phase_segments=phase_segments,
        workouts=allocated,
        workload_prescription=prescription,
    )


def _reserve_race_workouts(
    ordinary_workouts: Sequence[SkeletonWorkout],
    races: Sequence[PlanRace],
    *,
    starts_on: date,
    ends_on: date,
    max_runs_per_week: int,
    phase_by_day: Mapping[date, str],
) -> tuple[list[SkeletonWorkout], bool, bool]:
    included: dict[str, PlanRace] = {}
    for race in races:
        if starts_on <= race.race_date <= ends_on and race.race_goal_id and race.distance_meters > 0:
            included[race.race_goal_id] = race
    protected_dates = {race.race_date for race in included.values()}
    result = [workout for workout in ordinary_workouts if workout.scheduled_for not in protected_dates]
    result.extend(
        SkeletonWorkout(
            scheduled_for=race.race_date,
            workout_type="race",
            phase=phase_by_day[race.race_date],
            planned_duration_minutes=None,
            planned_distance_meters=race.distance_meters,
            race_goal_id=race.race_goal_id,
            race_name=race.name,
            race_priority=race.priority,
            race_goal_intent=race.goal_intent,
            is_target_race=race.is_target,
        )
        for race in included.values()
    )
    constrained = False
    conflict = len(protected_dates) < len(included)
    for week_start in _week_starts(starts_on, ends_on):
        week_end = min(week_start + timedelta(days=6), ends_on)
        week = [workout for workout in result if week_start <= workout.scheduled_for <= week_end]
        excess = max(0, len(week) - max_runs_per_week)
        removable = sorted(
            (workout for workout in week if workout.workout_type != "race"),
            key=lambda workout: (workout.workout_type == "long_run", workout.scheduled_for),
        )
        for workout in removable[:excess]:
            result.remove(workout)
        if excess > 0:
            constrained = True
    return sorted(result, key=lambda workout: (workout.scheduled_for, workout.race_goal_id or "")), constrained, conflict


def _quality_types_for_phase(phase: str, race_distance_meters: int | None, *, terrain_focus: bool) -> tuple[str, ...]:
    if terrain_focus:
        return ("hill",)
    if phase == "maintenance":
        return QUALITY_WORKOUT_TYPES
    short = race_distance_meters is not None and race_distance_meters <= 10_000
    if phase == "base":
        return ("tempo",)
    if phase == "build":
        return ("interval", "hill") if short else ("tempo", "hill")
    if phase == "peak":
        return ("interval", "tempo") if short else ("tempo",)
    return ()


def _focus_zone_for_workout(workout_type: str, phase: str, race_distance_meters: int | None) -> str | None:
    if workout_type == "interval":
        return "interval"
    if workout_type == "tempo":
        return "marathon" if phase == "peak" and race_distance_meters is not None and race_distance_meters >= 21_097 else "threshold"
    if workout_type == "hill":
        return "rpe_only"
    return None


def _adjust_training_around_races(
    workouts: Sequence[SkeletonWorkout],
    *,
    starts_on: date,
    prescription: WorkloadPrescription,
    max_runs_per_week: int,
    hard_session_limit: int,
) -> tuple[list[SkeletonWorkout], bool]:
    events = [workout for workout in workouts if workout.workout_type == "race"]
    adjusted: list[SkeletonWorkout] = []
    for workout in workouts:
        if workout.workout_type == "race":
            adjusted.append(workout)
            continue
        duration = workout.planned_duration_minutes
        workout_type = workout.workout_type
        focus_zone = workout.focus_zone
        week_index = (workout.scheduled_for - starts_on).days // 7
        if workout.phase == "taper":
            if prescription.weeks[week_index].phase != "taper":
                duration = max(1, round((duration or 0) * .65))
            if workout_type in QUALITY_WORKOUT_TYPES:
                workout_type, focus_zone = "easy_run", None
        for event in events:
            before, after = _supporting_race_window(event)
            offset = (workout.scheduled_for - event.scheduled_for).days
            if -before <= offset <= after:
                if workout_type in HARD_SESSION_WORKOUT_TYPES:
                    workout_type, focus_zone = "easy_run", None
                duration = min(duration or 30, 30)
        adjusted.append(replace(workout, workout_type=workout_type, planned_duration_minutes=duration, focus_zone=focus_zone))
    conflict = False
    result = list(adjusted)
    for week_index, week in enumerate(prescription.weeks):
        week_start = starts_on + timedelta(weeks=week_index)
        week_end = week_start + timedelta(days=6)
        weekly = [workout for workout in result if week_start <= workout.scheduled_for <= week_end]
        race_count = sum(workout.workout_type == "race" for workout in weekly)
        if race_count > hard_session_limit:
            conflict = True
        extra_hard = max(0, sum(workout.workout_type in HARD_SESSION_WORKOUT_TYPES for workout in weekly) + race_count - hard_session_limit)
        for workout in sorted(
            (item for item in weekly if item.workout_type in HARD_SESSION_WORKOUT_TYPES),
            key=lambda item: (item.workout_type == "long_run", item.scheduled_for),
        )[:extra_hard]:
            result[result.index(workout)] = replace(workout, workout_type="easy_run", focus_zone=None, planned_duration_minutes=min(workout.planned_duration_minutes or 30, 30))
    return result, conflict


def _supporting_race_window(event: SkeletonWorkout) -> tuple[int, int]:
    if event.is_target_race:
        return (0, 0)
    long_race = (event.planned_distance_meters or 0) >= 21_097
    if event.race_priority == "tune_up":
        return (2, 3) if long_race else (1, 1)
    return (3, 5) if long_race else (2, 2)


def validate_generated_plan(plan: TrainingPlan, skeleton: PlanSkeleton) -> list[str]:
    """Return deterministic completeness errors for a generated plan."""
    errors: list[str] = []
    if plan.starts_on != skeleton.starts_on or plan.ends_on != skeleton.ends_on:
        errors.append("plan dates do not match the skeleton")
    if plan.metadata.get("phase_segments") != skeleton.phase_segments:
        errors.append("phase segments do not match the skeleton")

    try:
        validate_phase_segments(plan)
    except DomainValidationError as error:
        errors.append(f"phase segments are invalid: {error}")

    for week_index, expected_workouts in enumerate(_skeleton_workouts_by_week(skeleton)):
        generated_workouts = _plan_workouts_for_week(plan, skeleton, week_index)
        if len(generated_workouts) != len(expected_workouts):
            errors.append(
                f"week {week_index} workout count is {len(generated_workouts)}; expected {len(expected_workouts)}"
            )
            continue
        if sorted(workout.scheduled_for for workout in generated_workouts) != sorted(
            workout.scheduled_for for workout in expected_workouts
        ):
            errors.append(f"week {week_index} workout dates do not match the skeleton")
            continue
        expected_by_date = {workout.scheduled_for: workout for workout in expected_workouts}
        for workout in generated_workouts:
            expected_workout = expected_by_date[workout.scheduled_for]
            if workout.phase != expected_workout.phase:
                errors.append(f"week {week_index} workout phase does not match the skeleton")
            if workout.workout_type != expected_workout.workout_type:
                errors.append(f"week {week_index} workout type does not match the skeleton")
            if workout.planned_duration_minutes != expected_workout.planned_duration_minutes:
                errors.append(f"week {week_index} workout planned duration does not match the skeleton")
            if workout.planned_distance_meters != expected_workout.planned_distance_meters:
                errors.append(f"week {week_index} workout planned distance does not match the skeleton")
            if workout.status != "planned":
                errors.append(f"week {week_index} workout status must be planned")
            if not _executable_load_within_skeleton(workout, expected_workout):
                errors.append(f"week {week_index} workout executable load exceeds the skeleton")
            elif plan.metadata.get("workload_policy_version") and not _executable_load_meets_floor(workout, expected_workout):
                errors.append(f"week {week_index} workout executable load is below the skeleton")
            if workout.workout_type in QUALITY_WORKOUT_TYPES and not _has_required_key_session_steps(workout):
                errors.append(f"week {week_index} {workout.workout_type} workout is missing required steps or numeric Targets")

    return errors


def repair_generated_plan(
    plan: TrainingPlan,
    skeleton: PlanSkeleton,
    reason: str,
    *,
    preserved_workouts: Sequence[Workout] = (),
) -> CompletionRepairResult:
    """Replace only incomplete skeleton weeks with stable template workouts."""
    repaired_week_indexes: list[int] = []
    repaired_workout_ids: list[str] = []
    repaired_workouts: list[Workout] = []

    for week_index, expected_workouts in enumerate(_skeleton_workouts_by_week(skeleton)):
        generated_workouts = _plan_workouts_for_week(plan, skeleton, week_index)
        week_start = skeleton.starts_on + timedelta(weeks=week_index)
        week_end = min(week_start + timedelta(days=6), skeleton.ends_on)
        original_week = [w for w in preserved_workouts if week_start <= w.scheduled_for <= week_end]
        if _week_is_complete(original_week, expected_workouts, enforce_floor=bool(plan.metadata.get("workload_policy_version"))):
            generated_workouts = original_week
        if _week_is_complete(generated_workouts, expected_workouts, enforce_floor=bool(plan.metadata.get("workload_policy_version"))):
            repaired_workouts.extend(generated_workouts)
            continue

        repaired_week_indexes.append(week_index)
        for skeleton_workout in expected_workouts:
            workout = _template_workout(skeleton_workout, week_index)
            repaired_workouts.append(workout)
            repaired_workout_ids.append(workout.id or "")

    metadata = dict(plan.metadata)
    metadata["phase_segments"] = list(skeleton.phase_segments)
    internal_metadata = metadata.get("internal")
    internal = dict(internal_metadata) if isinstance(internal_metadata, dict) else {}
    internal["completion_repair"] = {
        "repaired_week_indexes": repaired_week_indexes,
        "repaired_workout_ids": repaired_workout_ids,
        "reason": reason,
    }
    metadata["internal"] = internal

    repaired_plan = TrainingPlan.create(
        id=plan.id,
        user_id=plan.user_id,
        name=plan.name,
        race_id=plan.race_id,
        status=plan.status,
        starts_on=skeleton.starts_on,
        ends_on=skeleton.ends_on,
        workouts=tuple(repaired_workouts),
        metadata=metadata,
    )
    return CompletionRepairResult(
        plan=repaired_plan,
        repaired_week_indexes=repaired_week_indexes,
        repaired_workout_ids=repaired_workout_ids,
        reason=reason,
    )


def _selected_training_days(
    training_days: Sequence[str],
    preferred_long_run_day: str,
    max_runs_per_week: int,
) -> tuple[str, ...]:
    if preferred_long_run_day not in DAY_INDEX:
        raise ValueError(f"unsupported long run day: {preferred_long_run_day}")
    unique_days = tuple(dict.fromkeys(training_days))
    if any(day not in DAY_INDEX for day in unique_days):
        raise ValueError("preferred training days must be valid weekdays")
    if max_runs_per_week < 1:
        raise ValueError("maximum runs per week must be positive")
    if max_runs_per_week > len(DAY_INDEX):
        raise ValueError("maximum runs per week cannot exceed seven")

    ordered_days = (preferred_long_run_day,) + tuple(day for day in unique_days if day != preferred_long_run_day)
    return ordered_days + tuple(day for day in DAY_INDEX if day not in ordered_days)


def _week_starts(starts_on: date, ends_on: date) -> list[date]:
    return [starts_on + timedelta(weeks=week) for week in range((ends_on - starts_on).days // 7 + 1)]


def _scheduled_days(
    week_start: date,
    training_days: Sequence[str],
    ends_on: date,
    max_runs_per_week: int,
) -> list[date]:
    week_ends_on = min(week_start + timedelta(days=6), ends_on)
    scheduled_days = [
        week_start + timedelta(days=(DAY_INDEX[day] - week_start.weekday()) % 7)
        for day in training_days
    ]
    selected_days = [day for day in scheduled_days if day <= week_ends_on][:max_runs_per_week]
    return sorted(selected_days)


def _skeleton_workouts_by_week(skeleton: PlanSkeleton) -> list[list[SkeletonWorkout]]:
    weeks = _week_starts(skeleton.starts_on, skeleton.ends_on)
    return [
        [
            workout
            for workout in skeleton.workouts
            if week_start <= workout.scheduled_for <= min(week_start + timedelta(days=6), skeleton.ends_on)
        ]
        for week_start in weeks
    ]


def _plan_workouts_for_week(plan: TrainingPlan, skeleton: PlanSkeleton, week_index: int) -> list[Workout]:
    week_start = skeleton.starts_on + timedelta(weeks=week_index)
    week_ends_on = min(week_start + timedelta(days=6), skeleton.ends_on)
    return [workout for workout in plan.workouts if week_start <= workout.scheduled_for <= week_ends_on]


def _week_is_complete(generated_workouts: Sequence[Workout], expected_workouts: Sequence[SkeletonWorkout], *, enforce_floor: bool = False) -> bool:
    if len(generated_workouts) != len(expected_workouts):
        return False
    if sorted(workout.scheduled_for for workout in generated_workouts) != sorted(
        workout.scheduled_for for workout in expected_workouts
    ):
        return False
    expected_by_date = {workout.scheduled_for: workout for workout in expected_workouts}
    return all(
        workout.phase == expected_by_date[workout.scheduled_for].phase
        and workout.workout_type == expected_by_date[workout.scheduled_for].workout_type
        and workout.planned_duration_minutes == expected_by_date[workout.scheduled_for].planned_duration_minutes
        and workout.planned_distance_meters == expected_by_date[workout.scheduled_for].planned_distance_meters
        and workout.status == "planned"
        and _executable_load_within_skeleton(workout, expected_by_date[workout.scheduled_for])
        and (not enforce_floor or _executable_load_meets_floor(workout, expected_by_date[workout.scheduled_for]))
        and (workout.workout_type not in QUALITY_WORKOUT_TYPES or _has_required_key_session_steps(workout))
        for workout in generated_workouts
    )


def _executable_load_within_skeleton(workout: Workout, expected: SkeletonWorkout) -> bool:
    # Fixed conservative accounting, independent of model pace/finish claims.
    def distance_seconds(meters: int) -> int:
        return (meters * 600 + 999) // 1000

    def step_seconds(step: WorkoutStep) -> int:
        if step.step_type == "repeat":
            return int(step.repeat_count or 0) * sum(step_seconds(child) for child in step.steps)
        return max(step.duration_seconds or 0, distance_seconds(step.distance_meters or 0))

    budget = (
        expected.planned_duration_minutes * 60
        if expected.planned_duration_minutes is not None
        else distance_seconds(expected.planned_distance_meters or 0)
    )
    # A fixed allowance covers integer-second rounding, not repeat-scaled slack.
    return sum(step_seconds(step) for step in workout.steps) <= budget + 30


def _executable_load_meets_floor(workout: Workout, expected: SkeletonWorkout) -> bool:
    if expected.planned_duration_minutes is None:
        return True
    def seconds(step: WorkoutStep) -> int:
        if step.step_type == "repeat":
            return int(step.repeat_count or 0) * sum(seconds(child) for child in step.steps)
        return max(step.duration_seconds or 0, ((step.distance_meters or 0) * 600 + 999) // 1000)
    return sum(seconds(step) for step in workout.steps) >= expected.planned_duration_minutes * 60 * .9


def _has_required_key_session_steps(workout: Workout) -> bool:
    if not _steps_have_numeric_targets(workout.steps):
        return False
    step_types = {step.step_type for step in workout.steps}
    if not {"warmup", "cooldown"}.issubset(step_types):
        return False
    if workout.workout_type == "tempo":
        return any(step.step_type == "work" and step.target is not None for step in workout.steps)
    if workout.workout_type == "interval":
        return _has_complete_repeat_block(workout.steps, effort_step_type="work")
    if workout.workout_type == "hill":
        return _has_complete_repeat_block(workout.steps, effort_step_type="hill")
    return True


def _steps_have_numeric_targets(steps: Sequence[WorkoutStep]) -> bool:
    for step in steps:
        if step.step_type == "repeat":
            if not _steps_have_numeric_targets(step.steps):
                return False
            continue
        target = step.target
        if target is None:
            return False
        if target.kind == "rpe" and target.rpe is not None:
            continue
        if target.kind == "pace" and (target.pace_range_seconds_per_km is not None or target.rpe is not None):
            continue
        if target.kind == "heart_rate" and (target.heart_rate_range_bpm is not None or target.rpe is not None):
            continue
        return False
    return True


def _has_complete_repeat_block(steps: Sequence[WorkoutStep], *, effort_step_type: str) -> bool:
    return any(
        step.step_type == "repeat"
        and any(nested.step_type == effort_step_type and nested.target is not None for nested in step.steps)
        and any(nested.step_type == "recovery" for nested in step.steps)
        for step in steps
    )


def _template_workout(skeleton_workout: SkeletonWorkout, _week_index: int) -> Workout:
    return Workout.create(
        id=str(uuid4()),
        scheduled_for=skeleton_workout.scheduled_for,
        workout_type=skeleton_workout.workout_type,
        purpose=_template_purpose(skeleton_workout.workout_type),
        planned_duration_minutes=skeleton_workout.planned_duration_minutes,
        planned_distance_meters=skeleton_workout.planned_distance_meters,
        phase=skeleton_workout.phase,
        steps=_template_steps(skeleton_workout.workout_type, skeleton_workout.planned_duration_minutes),
    )


def _template_purpose(workout_type: str) -> str:
    return workout_purpose_zh(workout_type)


def _template_steps(workout_type: str, planned_duration_minutes: int | None) -> tuple[WorkoutStep, ...]:
    easy_target = WorkoutTarget.pace(zone="easy", rpe=3)
    total_seconds = (planned_duration_minutes or 20) * 60
    warmup = max(1, total_seconds // 4)
    cooldown = warmup
    main_seconds = total_seconds - warmup - cooldown
    if workout_type in {"easy_run", "long_run"}:
        return (
            WorkoutStep.create(
                step_type="free_run",
                duration_seconds=total_seconds,
                target=easy_target,
            ),
        )
    if workout_type == "tempo":
        return (
            WorkoutStep.create(step_type="warmup", duration_seconds=warmup, target=easy_target),
            WorkoutStep.create(
                step_type="work",
                duration_seconds=main_seconds,
                target=WorkoutTarget.pace(zone="threshold", rpe=7),
            ),
            WorkoutStep.create(step_type="cooldown", duration_seconds=cooldown, target=easy_target),
        )
    if workout_type == "interval":
        return (
            WorkoutStep.create(step_type="warmup", duration_seconds=warmup, target=easy_target),
            WorkoutStep.create(
                step_type="repeat",
                repeat_count=3,
                steps=(
                    WorkoutStep.create(
                        step_type="work",
                        duration_seconds=max(1, main_seconds // 6),
                        target=WorkoutTarget.pace(zone="interval", rpe=8),
                    ),
                    WorkoutStep.create(step_type="recovery", duration_seconds=max(1, main_seconds // 6), target=easy_target),
                ),
            ),
            WorkoutStep.create(step_type="cooldown", duration_seconds=cooldown, target=easy_target),
        )
    if workout_type == "hill":
        return (
            WorkoutStep.create(step_type="warmup", duration_seconds=warmup, target=easy_target),
            WorkoutStep.create(
                step_type="repeat",
                repeat_count=4,
                steps=(
                    WorkoutStep.create(step_type="hill", duration_seconds=max(1, main_seconds // 12), target=WorkoutTarget.rpe(8)),
                    WorkoutStep.create(step_type="recovery", duration_seconds=max(1, main_seconds // 6), target=easy_target),
                ),
            ),
            WorkoutStep.create(step_type="cooldown", duration_seconds=cooldown, target=easy_target),
        )
    return ()


def _is_safely_spaced(scheduled_for: date, hard_dates: Sequence[date]) -> bool:
    return all(abs((scheduled_for - hard_date).days) > 1 for hard_date in hard_dates)


def _build_phase_segments(
    starts_on: date,
    ends_on: date,
    plan_type: str,
    race_date: date | None,
    race_distance_meters: int | None = None,
) -> list[dict]:
    if plan_type == "maintenance":
        return [_phase_segment("maintenance", starts_on, ends_on)]
    if race_date is None or race_date > ends_on:
        return [_phase_segment("base", starts_on, ends_on)]

    race_is_inside_horizon = race_date is not None and starts_on <= race_date <= ends_on
    race_starts_on = race_date if race_is_inside_horizon else None
    taper_starts_on = None
    if race_starts_on is not None and race_starts_on > starts_on:
        taper_days = 14 if race_distance_meters is not None and race_distance_meters >= 21_097 else 7
        taper_starts_on = max(starts_on, race_starts_on - timedelta(days=taper_days))

    development_ends_on = (taper_starts_on or race_starts_on or date.fromordinal(ends_on.toordinal() + 1)) - timedelta(days=1)
    segments = _development_phase_segments(starts_on, development_ends_on)
    if taper_starts_on is not None:
        segments.append(_phase_segment("taper", taper_starts_on, race_starts_on - timedelta(days=1)))
    if race_starts_on is not None:
        segments.append(_phase_segment("race", race_starts_on, ends_on))
    return segments


def _development_phase_segments(starts_on: date, ends_on: date) -> list[dict]:
    if ends_on < starts_on:
        return []

    development_days = (ends_on - starts_on).days + 1
    if development_days < 3:
        return [_phase_segment("base", starts_on, ends_on)]

    base_days = ceil(development_days / 3)
    build_days = ceil((development_days - base_days) / 2)
    peak_days = development_days - base_days - build_days
    base_ends_on = starts_on + timedelta(days=base_days - 1)
    build_ends_on = base_ends_on + timedelta(days=build_days)
    return [
        _phase_segment("base", starts_on, base_ends_on),
        _phase_segment("build", base_ends_on + timedelta(days=1), build_ends_on),
        _phase_segment("peak", build_ends_on + timedelta(days=1), build_ends_on + timedelta(days=peak_days)),
    ]


def _phase_segment(phase: str, starts_on: date, ends_on: date) -> dict:
    if phase not in SUPPORTED_PLAN_PHASES:
        raise ValueError(f"unsupported plan phase: {phase}")
    return {"phase": phase, "starts_on": starts_on.isoformat(), "ends_on": ends_on.isoformat()}


def _phase_by_day(phase_segments: Sequence[dict]) -> dict[date, str]:
    phases: dict[date, str] = {}
    for segment in phase_segments:
        current_day = date.fromisoformat(segment["starts_on"])
        ends_on = date.fromisoformat(segment["ends_on"])
        while current_day <= ends_on:
            phases[current_day] = segment["phase"]
            current_day += timedelta(days=1)
    return phases
