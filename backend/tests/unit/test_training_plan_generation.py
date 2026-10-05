from dataclasses import replace
from datetime import date, timedelta
from uuid import UUID

import pytest

from src.application.training_plan_generation import (
    PlanRace,
    _week_starts,
    build_plan_skeleton,
    effective_hard_session_limit,
    projection_window,
    repair_generated_plan,
    select_race_strategy,
    validate_generated_plan,
)
from src.domain.training_plan import (
    HARD_SESSION_WORKOUT_TYPES,
    TrainingPlan,
    Workout,
    WorkoutStep,
    WorkoutTarget,
)


ANCHOR = date(2027, 1, 2)


def _race(*, race_id: str, race_date: date, priority: str = "primary") -> dict:
    return {"id": race_id, "race_date": race_date, "priority": priority}


def test_select_race_strategy_prioritizes_primary_races_over_nearer_lower_priorities() -> None:
    selection = select_race_strategy(
        [
            _race(race_id="tune-up", race_date=date(2027, 1, 9), priority="tune_up"),
            _race(race_id="secondary", race_date=date(2027, 1, 16), priority="secondary"),
            _race(race_id="primary", race_date=date(2027, 2, 1)),
        ],
        anchor=ANCHOR,
        explicit_race_id=None,
        force_maintenance=False,
    )

    assert selection.race_id == "primary"
    assert selection.plan_type == "race"
    assert selection.reason == "priority_and_date"


def test_select_race_strategy_chooses_nearest_race_with_same_priority() -> None:
    selection = select_race_strategy(
        [
            _race(race_id="later-primary", race_date=date(2027, 3, 1)),
            _race(race_id="nearer-primary", race_date=date(2027, 2, 1)),
        ],
        anchor=ANCHOR,
        explicit_race_id=None,
        force_maintenance=False,
    )

    assert selection.race_id == "nearer-primary"
    assert selection.reason == "priority_and_date"


def test_select_race_strategy_selects_a_race_on_the_anchor_date_by_default() -> None:
    selection = select_race_strategy(
        [_race(race_id="anchor-date", race_date=ANCHOR)],
        anchor=ANCHOR,
        explicit_race_id=None,
        force_maintenance=False,
    )

    assert selection.race_id == "anchor-date"
    assert selection.plan_type == "race"
    assert selection.reason == "priority_and_date"


def test_select_race_strategy_honors_an_explicit_future_race() -> None:
    selection = select_race_strategy(
        [
            _race(race_id="primary", race_date=date(2027, 2, 1)),
            _race(race_id="chosen-secondary", race_date=date(2027, 3, 1), priority="secondary"),
        ],
        anchor=ANCHOR,
        explicit_race_id="chosen-secondary",
        force_maintenance=False,
    )

    assert selection.race_id == "chosen-secondary"
    assert selection.plan_type == "race"
    assert selection.reason == "explicit_race"


def test_select_race_strategy_honors_an_explicit_race_on_the_anchor_date() -> None:
    selection = select_race_strategy(
        [_race(race_id="anchor-date", race_date=ANCHOR)],
        anchor=ANCHOR,
        explicit_race_id="anchor-date",
        force_maintenance=False,
    )

    assert selection.race_id == "anchor-date"
    assert selection.plan_type == "race"
    assert selection.reason == "explicit_race"


def test_select_race_strategy_maintenance_override_wins_over_explicit_race() -> None:
    selection = select_race_strategy(
        [_race(race_id="primary", race_date=date(2027, 2, 1))],
        anchor=ANCHOR,
        explicit_race_id="primary",
        force_maintenance=True,
    )

    assert selection.race_id is None
    assert selection.plan_type == "maintenance"
    assert selection.reason == "maintenance_forced"


def test_select_race_strategy_uses_maintenance_when_no_future_race_exists() -> None:
    selection = select_race_strategy(
        [_race(race_id="past", race_date=date(2027, 1, 1))],
        anchor=ANCHOR,
        explicit_race_id=None,
        force_maintenance=False,
    )

    assert selection.race_id is None
    assert selection.plan_type == "maintenance"
    assert selection.reason == "no_future_race"


def test_projection_window_caps_a_race_farther_than_sixteen_weeks() -> None:
    race_date = ANCHOR + timedelta(weeks=20)

    starts_on, ends_on = projection_window(ANCHOR, race_date, "race")

    assert starts_on == ANCHOR
    assert ends_on == ANCHOR + timedelta(weeks=16) - timedelta(days=1)


def test_projection_window_ends_on_race_day_inside_sixteen_week_horizon() -> None:
    race_date = ANCHOR + timedelta(weeks=8)

    assert projection_window(ANCHOR, race_date, "race") == (ANCHOR, race_date)


def test_projection_window_uses_four_full_weeks_for_maintenance() -> None:
    starts_on, ends_on = projection_window(ANCHOR, None, "maintenance")

    assert starts_on == ANCHOR
    assert ends_on == ANCHOR + timedelta(weeks=4) - timedelta(days=1)


def _skeleton(**overrides):
    arguments = {
        "starts_on": date(2027, 1, 4),
        "ends_on": date(2027, 1, 31),
        "plan_type": "maintenance",
        "race_date": None,
        "preferred_training_days": ("tuesday", "thursday", "sunday"),
        "preferred_long_run_day": "sunday",
        "max_runs_per_week": 3,
        "max_hard_sessions_per_week": 2,
        "injury_status": "none",
        "current_weekly_mileage_km": 40,
        "experience_level": "advanced",
    }
    arguments.update(overrides)
    return build_plan_skeleton(**arguments)


def test_in_horizon_races_replace_runs_and_reserve_off_day_events() -> None:
    secondary = PlanRace("secondary-1", "Spring 10K", date(2027, 1, 12), 10_000, "secondary", False, "perform")
    tune_up = PlanRace("tune-1", "Park 5K", date(2027, 1, 16), 5_000, "tune_up", False, None)
    skeleton = _skeleton(races=(secondary, tune_up))

    races = [workout for workout in skeleton.workouts if workout.workout_type == "race"]
    assert {(workout.race_goal_id, workout.scheduled_for, workout.planned_distance_meters) for workout in races} == {
        ("secondary-1", date(2027, 1, 12), 10_000),
        ("tune-1", date(2027, 1, 16), 5_000),
    }
    assert all(workout.planned_duration_minutes is None for workout in races)
    assert all(sum(workout.scheduled_for == race.scheduled_for for workout in skeleton.workouts if workout.workout_type != "race") == 0 for race in races)
    assert len([workout for workout in skeleton.workouts if date(2027, 1, 11) <= workout.scheduled_for <= date(2027, 1, 17)]) <= 3


def test_same_day_races_survive_run_cap_and_report_constraint() -> None:
    day = date(2027, 1, 12)
    races = (
        PlanRace("race-1", "First", day, 5_000, "secondary", False, None),
        PlanRace("race-2", "Second", day, 10_000, "tune_up", False, None),
    )
    skeleton = _skeleton(races=races, max_runs_per_week=1)

    assert [workout.race_goal_id for workout in skeleton.workouts if workout.workout_type == "race"] == ["race-1", "race-2"]
    assert not any(workout.workout_type != "race" and date(2027, 1, 11) <= workout.scheduled_for <= date(2027, 1, 17) for workout in skeleton.workouts)
    assert "constrained_schedule" in skeleton.workload_prescription.assessment.factors


def test_target_race_appears_once_even_when_already_a_preferred_day() -> None:
    event = date(2027, 1, 31)
    target = PlanRace("target-1", "Goal Race", event, 21_097, "primary", True, "perform")
    skeleton = _skeleton(plan_type="race", race_date=event, race_distance_meters=21_097, races=(target,))

    assert [workout.race_goal_id for workout in skeleton.workouts if workout.scheduled_for == event] == ["target-1"]
    assert skeleton.workouts[-1].workout_type == "race"


def test_off_day_race_on_phase_boundary_uses_its_calendar_phase() -> None:
    event = PlanRace("support-1", "Monday 5K", date(2027, 1, 11), 5_000, "tune_up", False, None)
    skeleton = _skeleton(plan_type="race", race_date=date(2027, 1, 31), race_distance_meters=10_000, races=(event,))

    race = next(workout for workout in skeleton.workouts if workout.race_goal_id == "support-1")
    assert race.phase == "build"


def test_build_plan_skeleton_creates_four_week_maintenance_block() -> None:
    skeleton = _skeleton()

    assert (skeleton.starts_on, skeleton.ends_on) == (date(2027, 1, 4), date(2027, 1, 31))
    assert skeleton.phase_segments == [
        {"phase": "maintenance", "starts_on": "2027-01-04", "ends_on": "2027-01-31"}
    ]


def test_missing_baseline_uses_low_risk_load_and_capacity() -> None:
    skeleton = _skeleton(current_weekly_mileage_km=None, experience_level=None)
    assert max(w.planned_duration_minutes for w in skeleton.workouts) <= 30
    assert not any(w.workout_type in {"interval", "tempo", "hill"} for w in skeleton.workouts)


def test_established_beginner_can_have_one_quality_session_beside_long_run() -> None:
    skeleton = _skeleton(
        starts_on=date(2026, 10, 3), ends_on=date(2026, 11, 21),
        plan_type="race", race_date=date(2026, 11, 21), race_distance_meters=40000,
        preferred_training_days=("tuesday", "sunday", "wednesday", "friday", "saturday"),
        max_runs_per_week=5, max_hard_sessions_per_week=2,
        current_weekly_mileage_km=40, experience_level="beginner",
    )

    quality = {"interval", "tempo", "hill"}
    assert any(workout.workout_type in quality for workout in skeleton.workouts)
    for week in range(7):
        week_workouts = [workout for workout in skeleton.workouts if (workout.scheduled_for - skeleton.starts_on).days // 7 == week]
        assert sum(workout.workout_type in quality | {"long_run"} for workout in week_workouts) <= 2


def test_lower_mileage_beginner_keeps_conservative_aerobic_skeleton() -> None:
    skeleton = _skeleton(
        current_weekly_mileage_km=30, experience_level="beginner",
        max_runs_per_week=5, max_hard_sessions_per_week=2,
    )

    assert not any(workout.workout_type in {"interval", "tempo", "hill"} for workout in skeleton.workouts)


def test_mileage_not_experience_determines_starting_load() -> None:
    beginner = _skeleton(current_weekly_mileage_km=20, experience_level="beginner")
    experienced = _skeleton(current_weekly_mileage_km=40, experience_level="advanced")
    same_mileage = _skeleton(current_weekly_mileage_km=40, experience_level="beginner")
    total = lambda s: sum(w.planned_duration_minutes for w in s.workouts)
    assert total(beginner) < total(same_mileage) == total(experienced)
    weeks = [sum(w.planned_duration_minutes for w in experienced.workouts if (w.scheduled_for - experienced.starts_on).days // 7 == i) for i in range(4)]
    assert weeks[0] < weeks[1] < weeks[2]
    assert weeks[3] < weeks[0]


def test_40km_three_day_plan_builds_beyond_old_long_run_and_reports_gap() -> None:
    from src.application.training_workload_policy import RaceDemand

    skeleton = _skeleton(
        plan_type="race", race_date=date(2027, 4, 25), ends_on=date(2027, 4, 25),
        race_distance_meters=40_000, current_weekly_mileage_km=25,
        race_demand=RaceDemand(40_000, date(2027, 4, 25), None, None, None, "technical", None, "complete"),
    )
    assert max(workout.planned_duration_minutes for workout in skeleton.workouts if workout.workout_type == "long_run") > 70
    assert skeleton.workload_prescription.assessment.status == "gap"
    assert "weekly_volume" in skeleton.workload_prescription.assessment.factors


def test_high_capacity_40km_plan_can_exceed_old_120_minute_ceiling() -> None:
    from src.application.training_workload_policy import RaceDemand, CapacitySnapshot

    capacity = CapacitySnapshot("activities", "high", 320, 53, 150, date(2026, 12, 1), date(2026, 12, 28), 12, ())
    skeleton = _skeleton(plan_type="race", race_date=date(2027, 4, 25), ends_on=date(2027, 4, 25), race_distance_meters=40_000, current_weekly_mileage_km=53, capacity_snapshot=capacity, race_demand=RaceDemand(40_000, date(2027, 4, 25), None, None, None, None, None, "complete"))
    assert max(workout.planned_duration_minutes for workout in skeleton.workouts if workout.workout_type == "long_run") > 120


def test_one_run_schedule_assesses_actual_minutes_not_unallocated_budget() -> None:
    from src.application.training_workload_policy import RaceDemand, CapacitySnapshot

    capacity = CapacitySnapshot("activities", "high", 360, 60, 170, date(2026, 12, 1), date(2026, 12, 28), 12, ())
    skeleton = _skeleton(plan_type="race", race_date=date(2027, 4, 25), ends_on=date(2027, 4, 25), preferred_training_days=("sunday",), max_runs_per_week=1, race_distance_meters=40_000, capacity_snapshot=capacity, race_demand=RaceDemand(40_000, date(2027, 4, 25), None, None, None, None, None, "complete"))
    assert all(sum(workout.planned_duration_minutes for workout in skeleton.workouts if (workout.scheduled_for - skeleton.starts_on).days // 7 == week) <= 180 for week in range(16))
    assert skeleton.workload_prescription.assessment.status == "gap"
    assert "weekly_volume" in skeleton.workload_prescription.assessment.factors
    assert all(week.long_run_minutes == 0 for week in skeleton.workload_prescription.weeks)
    assert all(week.target_minutes <= 90 for week in skeleton.workload_prescription.weeks)
    assert all(week.target_minutes == sum(workout.planned_duration_minutes for workout in skeleton.workouts if (workout.scheduled_for - skeleton.starts_on).days // 7 == week.week_index) for week in skeleton.workload_prescription.weeks)


def test_technical_race_hill_exposure_occurs_in_final_eight_development_weeks() -> None:
    from src.application.training_workload_policy import RaceDemand, CapacitySnapshot

    capacity = CapacitySnapshot("activities", "high", 340, 56, 155, date(2026, 12, 1), date(2026, 12, 28), 12, ())
    skeleton = _skeleton(plan_type="race", race_date=date(2027, 4, 25), ends_on=date(2027, 4, 25), race_distance_meters=40_000, capacity_snapshot=capacity, race_demand=RaceDemand(40_000, date(2027, 4, 25), None, None, None, "technical", None, "complete"))
    focus_weeks = [week.week_index for week in skeleton.workload_prescription.weeks if week.terrain_focus]
    assert len(focus_weeks) == 2
    assert all(any(workout.workout_type == "hill" for workout in skeleton.workouts if (workout.scheduled_for - skeleton.starts_on).days // 7 == index) for index in focus_weeks)
    assert "terrain_exposure" not in skeleton.workload_prescription.assessment.factors


def test_race_distance_changes_key_sessions_and_long_run_progression() -> None:
    args = dict(plan_type="race", race_date=date(2027, 2, 28), ends_on=date(2027, 2, 28), current_weekly_mileage_km=40, experience_level="advanced")
    short = _skeleton(**args, race_distance_meters=5000)
    long = _skeleton(**args, race_distance_meters=42195)
    assert short.workouts != long.workouts
    assert sum(w.planned_duration_minutes for w in long.workouts if w.workout_type == "long_run") > sum(w.planned_duration_minutes for w in short.workouts if w.workout_type == "long_run")
    assert any(w.workout_type == "interval" for w in short.workouts)
    assert any(w.workout_type == "tempo" for w in long.workouts)


def test_far_future_race_stays_aerobic_without_peak_or_taper() -> None:
    skeleton = _skeleton(plan_type="race", race_date=date(2027, 12, 1), ends_on=date(2027, 4, 25), current_weekly_mileage_km=40, experience_level="advanced")
    assert {s["phase"] for s in skeleton.phase_segments} <= {"base", "build"}
    assert not any(w.workout_type in {"interval", "tempo", "hill"} for w in skeleton.workouts)


def test_build_plan_skeleton_creates_contiguous_race_phase_coverage() -> None:
    skeleton = _skeleton(
        ends_on=date(2027, 2, 28),
        plan_type="race",
        race_date=date(2027, 2, 28),
    )

    assert skeleton.phase_segments[0]["starts_on"] == "2027-01-04"
    assert skeleton.phase_segments[-1]["ends_on"] == "2027-02-28"
    assert {segment["phase"] for segment in skeleton.phase_segments} == {
        "base",
        "build",
        "peak",
        "taper",
        "race",
    }
    assert all(
        current["ends_on"] == (date.fromisoformat(next_segment["starts_on"]) - timedelta(days=1)).isoformat()
        for current, next_segment in zip(skeleton.phase_segments, skeleton.phase_segments[1:])
    )


def test_build_plan_skeleton_matches_weekly_baseline_capacity() -> None:
    skeleton = _skeleton(max_runs_per_week=3)

    for week_start in (date(2027, 1, 4), date(2027, 1, 11), date(2027, 1, 18), date(2027, 1, 25)):
        assert sum(week_start <= workout.scheduled_for <= week_start + timedelta(days=6) for workout in skeleton.workouts) == 3


def test_build_plan_skeleton_uses_canonical_hard_session_types() -> None:
    skeleton = _skeleton(ends_on=date(2027, 2, 28))

    assert {workout.workout_type for workout in skeleton.workouts if workout.workout_type in HARD_SESSION_WORKOUT_TYPES} >= {
        "interval",
        "tempo",
        "hill",
        "long_run",
    }


def test_build_plan_skeleton_never_schedules_adjacent_hard_sessions() -> None:
    skeleton = _skeleton()
    hard_dates = sorted(
        workout.scheduled_for for workout in skeleton.workouts if workout.workout_type in HARD_SESSION_WORKOUT_TYPES
    )

    assert all(later - earlier > timedelta(days=1) for earlier, later in zip(hard_dates, hard_dates[1:]))


def test_build_plan_skeleton_keeps_long_runs_away_from_other_hard_sessions() -> None:
    skeleton = _skeleton()
    hard_workouts = [workout for workout in skeleton.workouts if workout.workout_type in HARD_SESSION_WORKOUT_TYPES]

    for long_run in (workout for workout in hard_workouts if workout.workout_type == "long_run"):
        assert all(
            workout.workout_type == "long_run" or abs((workout.scheduled_for - long_run.scheduled_for).days) > 1
            for workout in hard_workouts
        )


def test_build_plan_skeleton_caps_low_volume_athletes_at_one_hard_session_per_week() -> None:
    skeleton = _skeleton(max_runs_per_week=2, max_hard_sessions_per_week=2)

    assert effective_hard_session_limit(2, 2, "none") == 1
    for week_start in (date(2027, 1, 4), date(2027, 1, 11), date(2027, 1, 18), date(2027, 1, 25)):
        assert sum(
            week_start <= workout.scheduled_for <= week_start + timedelta(days=6)
            and workout.workout_type in HARD_SESSION_WORKOUT_TYPES
            for workout in skeleton.workouts
        ) <= 1


@pytest.mark.parametrize("max_runs_per_week", range(3, 8))
def test_build_plan_skeleton_respects_effective_weekly_hard_session_limit(max_runs_per_week: int) -> None:
    skeleton = _skeleton(max_runs_per_week=max_runs_per_week)
    hard_session_limit = effective_hard_session_limit(max_runs_per_week, 2, "none")

    for week_start in _week_starts(skeleton.starts_on, skeleton.ends_on):
        hard_session_count = sum(
            week_start <= workout.scheduled_for <= week_start + timedelta(days=6)
            and workout.workout_type in HARD_SESSION_WORKOUT_TYPES
            for workout in skeleton.workouts
        )
        assert hard_session_count <= hard_session_limit


def test_build_plan_skeleton_preserves_preferred_long_run_day_when_preferred_days_are_adjacent() -> None:
    skeleton = _skeleton(
        preferred_training_days=("saturday", "sunday"),
        preferred_long_run_day="sunday",
        max_runs_per_week=3,
    )

    sunday_workouts = [workout for workout in skeleton.workouts if workout.scheduled_for.weekday() == 6]

    assert sunday_workouts
    assert all(workout.workout_type == "long_run" for workout in sunday_workouts)


def test_build_plan_skeleton_uses_available_days_in_a_final_partial_week() -> None:
    skeleton = _skeleton(
        ends_on=date(2027, 2, 1),
        plan_type="race",
        race_date=date(2027, 2, 1),
    )

    assert [workout.scheduled_for for workout in skeleton.workouts if workout.scheduled_for >= date(2027, 2, 1)] == [
        date(2027, 2, 1)
    ]


def test_build_plan_skeleton_fills_weekly_capacity_beyond_preferred_day_count() -> None:
    skeleton = _skeleton(
        preferred_training_days=("tuesday", "sunday"),
        max_runs_per_week=4,
    )

    for week_start in (date(2027, 1, 4), date(2027, 1, 11), date(2027, 1, 18), date(2027, 1, 25)):
        assert sum(week_start <= workout.scheduled_for <= week_start + timedelta(days=6) for workout in skeleton.workouts) == 4


def test_effective_hard_session_limit_defaults_to_two_and_allows_zero() -> None:
    assert effective_hard_session_limit(5, injury_status="none") == 2
    assert effective_hard_session_limit(5, max_hard_sessions_per_week=0, injury_status="none") == 0


@pytest.mark.parametrize("max_hard_sessions_per_week", [-1, 3])
def test_effective_hard_session_limit_rejects_out_of_range_capacity(max_hard_sessions_per_week: int) -> None:
    with pytest.raises(ValueError, match="maximum hard sessions per week must be between 0 and 2"):
        effective_hard_session_limit(5, max_hard_sessions_per_week, "none")


@pytest.mark.parametrize("injury_status", ["current", "recent"])
def test_effective_hard_session_limit_caps_current_or_recent_injury_at_one(injury_status: str) -> None:
    assert effective_hard_session_limit(5, injury_status=injury_status) == 1


def test_week_starts_returns_exact_horizon_week_count() -> None:
    assert _week_starts(date(2027, 1, 4), date(2027, 1, 31)) == [
        date(2027, 1, 4),
        date(2027, 1, 11),
        date(2027, 1, 18),
        date(2027, 1, 25),
    ]


def _generated_plan(skeleton, workouts: tuple[Workout, ...]) -> TrainingPlan:
    return TrainingPlan.create(
        user_id="athlete-1",
        name="Generated plan",
        starts_on=skeleton.starts_on,
        ends_on=skeleton.ends_on,
        workouts=workouts,
        metadata={"phase_segments": skeleton.phase_segments},
    )


def _complete_workout(skeleton_workout, *, id: str | None = None) -> Workout:
    easy_target = WorkoutTarget.pace(zone="easy", rpe=3)
    steps = ()
    if skeleton_workout.workout_type == "tempo":
        steps = (
            WorkoutStep.create(step_type="warmup", duration_seconds=600, target=easy_target),
            WorkoutStep.create(
                step_type="work",
                duration_seconds=1_500,
                target=WorkoutTarget.pace(zone="threshold", rpe=7),
            ),
            WorkoutStep.create(step_type="cooldown", duration_seconds=600, target=easy_target),
        )
    if skeleton_workout.workout_type == "interval":
        steps = (
            WorkoutStep.create(step_type="warmup", duration_seconds=600, target=easy_target),
            WorkoutStep.create(
                step_type="repeat",
                repeat_count=3,
                steps=(
                    WorkoutStep.create(
                        step_type="work",
                        duration_seconds=300,
                        target=WorkoutTarget.pace(zone="interval", rpe=8),
                    ),
                    WorkoutStep.create(step_type="recovery", duration_seconds=180, target=easy_target),
                ),
            ),
            WorkoutStep.create(step_type="cooldown", duration_seconds=600, target=easy_target),
        )
    if skeleton_workout.workout_type == "hill":
        steps = (
            WorkoutStep.create(step_type="warmup", duration_seconds=600, target=easy_target),
            WorkoutStep.create(
                step_type="repeat",
                repeat_count=4,
                steps=(
                    WorkoutStep.create(
                        step_type="hill",
                        duration_seconds=120,
                        target=WorkoutTarget.rpe(8),
                    ),
                    WorkoutStep.create(step_type="recovery", duration_seconds=300, target=easy_target),
                ),
            ),
            WorkoutStep.create(step_type="cooldown", duration_seconds=600, target=easy_target),
        )
    if steps:
        total = sum(step.total_duration_seconds for step in steps)
        factor = skeleton_workout.planned_duration_minutes * 60 / total
        def scale(step):
            return replace(step, duration_seconds=max(1, round(step.duration_seconds * factor)) if step.duration_seconds else None, steps=tuple(scale(s) for s in step.steps))
        steps = tuple(scale(step) for step in steps)
    return Workout.create(
        id=id,
        scheduled_for=skeleton_workout.scheduled_for,
        workout_type=skeleton_workout.workout_type,
        purpose="Scheduled training",
        planned_duration_minutes=skeleton_workout.planned_duration_minutes,
        planned_distance_meters=skeleton_workout.planned_distance_meters,
        phase=skeleton_workout.phase,
        steps=steps,
    )


def test_validate_generated_plan_reports_missing_weeks_in_an_eight_week_skeleton() -> None:
    skeleton = _skeleton(ends_on=date(2027, 2, 28))
    first_two_weeks = tuple(
        _complete_workout(workout) for workout in skeleton.workouts if workout.scheduled_for < date(2027, 1, 18)
    )
    plan = _generated_plan(skeleton, first_two_weeks)

    errors = validate_generated_plan(plan, skeleton)

    assert any("week 2" in error and "workout count" in error for error in errors)
    assert any("week 7" in error and "workout count" in error for error in errors)


def test_validate_generated_plan_reports_invalid_phase_segments() -> None:
    skeleton = _skeleton()
    plan = TrainingPlan.create(
        user_id="athlete-1",
        name="Generated plan",
        starts_on=skeleton.starts_on,
        ends_on=skeleton.ends_on,
        metadata={"phase_segments": []},
    )

    errors = validate_generated_plan(plan, skeleton)

    assert any("phase segments" in error for error in errors)


def test_validate_generated_plan_reports_interval_without_required_steps() -> None:
    skeleton = _skeleton(ends_on=date(2027, 2, 28))
    generated_workouts = tuple(_complete_workout(workout) for workout in skeleton.workouts)
    interval_index = next(index for index, workout in enumerate(generated_workouts) if workout.workout_type == "interval")
    incomplete_interval = Workout.create(
        scheduled_for=generated_workouts[interval_index].scheduled_for,
        workout_type="interval",
        purpose="Incomplete interval session",
        planned_duration_minutes=45,
        phase=generated_workouts[interval_index].phase,
        steps=(WorkoutStep.create(step_type="warmup", duration_seconds=2_400),),
    )
    plan = _generated_plan(
        skeleton,
        generated_workouts[:interval_index] + (incomplete_interval,) + generated_workouts[interval_index + 1 :],
    )

    errors = validate_generated_plan(plan, skeleton)

    assert any("interval" in error and "required steps" in error for error in errors)


def test_generated_workout_steps_must_cover_at_least_ninety_percent_of_duration() -> None:
    from src.application.training_plan_generation import _template_steps
    skeleton = _skeleton(max_hard_sessions_per_week=0)
    workouts = tuple(replace(_complete_workout(workout), steps=_template_steps(workout.workout_type, workout.planned_duration_minutes)) for workout in skeleton.workouts)
    first = workouts[0]
    short = replace(first, steps=(WorkoutStep.create(step_type="free_run", distance_meters=1000),))
    plan = replace(_generated_plan(skeleton, (short,) + workouts[1:]), metadata={"phase_segments": skeleton.phase_segments, "workload_policy_version": "race-workload-v1"})
    assert any("executable load" in error for error in validate_generated_plan(plan, skeleton))
    near = replace(first, steps=(WorkoutStep.create(step_type="free_run", distance_meters=round(first.planned_duration_minutes * 100 * .92)),))
    plan = replace(_generated_plan(skeleton, (near,) + workouts[1:]), metadata={"phase_segments": skeleton.phase_segments, "workload_policy_version": "race-workload-v1"})
    assert not any("executable load" in error for error in validate_generated_plan(plan, skeleton))


@pytest.mark.parametrize(
    ("workout_type", "effort_step_type"),
    [("tempo", "work"), ("interval", "work"), ("hill", "hill")],
)
def test_validate_generated_plan_rejects_key_session_effort_without_target(
    workout_type: str,
    effort_step_type: str,
) -> None:
    skeleton = _skeleton(ends_on=date(2027, 2, 28))
    generated_workouts = tuple(_complete_workout(workout) for workout in skeleton.workouts)
    changed_index = next(
        index for index, workout in enumerate(generated_workouts) if workout.workout_type == workout_type
    )
    original = generated_workouts[changed_index]
    if workout_type == "tempo":
        malformed_steps = tuple(
            replace(step, target=None) if step.step_type == effort_step_type else step for step in original.steps
        )
    else:
        malformed_steps = tuple(
            replace(
                step,
                steps=tuple(
                    replace(nested_step, target=None)
                    if nested_step.step_type == effort_step_type
                    else nested_step
                    for nested_step in step.steps
                ),
            )
            if step.step_type == "repeat"
            else step
            for step in original.steps
        )
    malformed_workout = replace(original, steps=malformed_steps)
    plan = _generated_plan(
        skeleton,
        generated_workouts[:changed_index] + (malformed_workout,) + generated_workouts[changed_index + 1 :],
    )

    errors = validate_generated_plan(plan, skeleton)

    assert any(workout_type in error and "required steps" in error for error in errors)


@pytest.mark.parametrize(("workout_type", "effort_step_type"), [("interval", "work"), ("hill", "hill")])
def test_validate_generated_plan_rejects_repeat_block_without_recovery(
    workout_type: str,
    effort_step_type: str,
) -> None:
    skeleton = _skeleton(ends_on=date(2027, 2, 28))
    generated_workouts = tuple(_complete_workout(workout) for workout in skeleton.workouts)
    changed_index = next(
        index for index, workout in enumerate(generated_workouts) if workout.workout_type == workout_type
    )
    original = generated_workouts[changed_index]
    malformed_steps = tuple(
        replace(step, steps=tuple(nested for nested in step.steps if nested.step_type == effort_step_type))
        if step.step_type == "repeat"
        else step
        for step in original.steps
    )
    malformed_workout = replace(original, planned_duration_minutes=None, steps=malformed_steps)
    plan = _generated_plan(
        skeleton,
        generated_workouts[:changed_index] + (malformed_workout,) + generated_workouts[changed_index + 1 :],
    )

    errors = validate_generated_plan(plan, skeleton)

    assert any(workout_type in error and "required steps" in error for error in errors)


def test_repair_generated_plan_replaces_only_invalid_weeks_and_records_metadata() -> None:
    skeleton = _skeleton(ends_on=date(2027, 2, 28))
    first_week = tuple(
        _complete_workout(workout, id=f"preserved-{index}")
        for index, workout in enumerate(skeleton.workouts)
        if workout.scheduled_for < date(2027, 1, 11)
    )
    partial_plan = _generated_plan(skeleton, first_week)

    result = repair_generated_plan(partial_plan, skeleton, "model output was incomplete")

    assert result.repaired_week_indexes == [1, 2, 3, 4, 5, 6, 7]
    assert result.reason == "model output was incomplete"
    assert result.plan.workouts[: len(first_week)] == first_week
    assert result.repaired_workout_ids
    assert validate_generated_plan(result.plan, skeleton) == []
    assert result.plan.metadata["internal"]["completion_repair"] == {
        "repaired_week_indexes": result.repaired_week_indexes,
        "repaired_workout_ids": result.repaired_workout_ids,
        "reason": "model output was incomplete",
    }


def test_repair_generated_plan_uses_persistence_safe_uuid_workout_ids() -> None:
    skeleton = _skeleton()
    result = repair_generated_plan(_generated_plan(skeleton, ()), skeleton, "model output was incomplete")

    assert result.repaired_workout_ids
    assert all(len(workout_id) <= 36 for workout_id in result.repaired_workout_ids)
    assert all(str(UUID(workout_id)) == workout_id for workout_id in result.repaired_workout_ids)


def test_repair_generated_plan_does_not_reuse_ids_across_overlapping_repairs() -> None:
    skeleton = _skeleton()
    incomplete_plan = _generated_plan(skeleton, ())

    first_result = repair_generated_plan(incomplete_plan, skeleton, "first incomplete output")
    second_result = repair_generated_plan(incomplete_plan, skeleton, "second incomplete output")

    assert set(first_result.repaired_workout_ids).isdisjoint(second_result.repaired_workout_ids)


def test_validate_generated_plan_reports_workout_type_that_differs_from_skeleton() -> None:
    skeleton = _skeleton(ends_on=date(2027, 2, 28))
    generated_workouts = tuple(_complete_workout(workout) for workout in skeleton.workouts)
    changed_index = next(index for index, workout in enumerate(generated_workouts) if workout.workout_type != "easy_run")
    changed_workout = replace(generated_workouts[changed_index], workout_type="easy_run")
    plan = _generated_plan(
        skeleton,
        generated_workouts[:changed_index] + (changed_workout,) + generated_workouts[changed_index + 1 :],
    )

    errors = validate_generated_plan(plan, skeleton)

    assert any("workout type does not match the skeleton" in error for error in errors)


def test_validate_generated_plan_rejects_model_load_and_status_that_differ_from_the_skeleton() -> None:
    skeleton = _skeleton()
    generated_workouts = tuple(_complete_workout(workout) for workout in skeleton.workouts)
    changed_index = next(index for index, workout in enumerate(generated_workouts) if not workout.steps)
    tampered = replace(
        generated_workouts[changed_index],
        planned_duration_minutes=(generated_workouts[changed_index].planned_duration_minutes or 0) + 30,
        planned_distance_meters=(generated_workouts[changed_index].planned_distance_meters or 0) + 1_000,
        status="completed",
    )
    plan = _generated_plan(
        skeleton,
        generated_workouts[:changed_index] + (tampered,) + generated_workouts[changed_index + 1 :],
    )

    errors = validate_generated_plan(plan, skeleton)

    assert any("planned duration does not match the skeleton" in error for error in errors)
    assert any("planned distance does not match the skeleton" in error for error in errors)
    assert any("status must be planned" in error for error in errors)


def test_repair_generated_plan_replaces_complete_week_with_changed_workout_type() -> None:
    skeleton = _skeleton(ends_on=date(2027, 2, 28))
    generated_workouts = tuple(_complete_workout(workout, id=f"generated-{index}") for index, workout in enumerate(skeleton.workouts))
    changed_index = next(index for index, workout in enumerate(generated_workouts) if workout.workout_type != "easy_run")
    changed_workout = replace(generated_workouts[changed_index], workout_type="easy_run")
    plan = _generated_plan(
        skeleton,
        generated_workouts[:changed_index] + (changed_workout,) + generated_workouts[changed_index + 1 :],
    )

    result = repair_generated_plan(plan, skeleton, "workout type changed")

    assert result.repaired_week_indexes == [0]
    assert [workout.workout_type for workout in result.plan.workouts[:3]] == [
        workout.workout_type for workout in skeleton.workouts[:3]
    ]
    assert result.plan.workouts[3:] == generated_workouts[3:]


def test_validate_generated_plan_requires_canonical_skeleton_phase_timeline() -> None:
    skeleton = _skeleton(
        ends_on=date(2027, 2, 28),
        plan_type="race",
        race_date=date(2027, 2, 28),
    )
    shifted_segments = [dict(segment) for segment in skeleton.phase_segments]
    original_boundary = date.fromisoformat(shifted_segments[0]["ends_on"])
    shifted_segments[0]["ends_on"] = (original_boundary + timedelta(days=1)).isoformat()
    shifted_segments[1]["starts_on"] = (original_boundary + timedelta(days=1)).isoformat()
    generated_workouts = tuple(
        replace(
            _complete_workout(workout),
            phase=next(
                segment["phase"]
                for segment in shifted_segments
                if date.fromisoformat(segment["starts_on"])
                <= workout.scheduled_for
                <= date.fromisoformat(segment["ends_on"])
            ),
        )
        for workout in skeleton.workouts
    )
    plan = TrainingPlan.create(
        user_id="athlete-1",
        name="Generated plan",
        starts_on=skeleton.starts_on,
        ends_on=skeleton.ends_on,
        workouts=generated_workouts,
        metadata={"phase_segments": shifted_segments},
    )

    errors = validate_generated_plan(plan, skeleton)

    assert any("phase segments do not match the skeleton" in error for error in errors)
