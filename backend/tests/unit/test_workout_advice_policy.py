from datetime import date, datetime, timezone

import pytest

from src.domain.training_plan import Workout, WorkoutStep, WorkoutTarget
from src.domain.workout_advice import AdviceEvidence, WorkoutAdviceConstraints, assess_workout_advice


TODAY = datetime(2026, 10, 16, 1, tzinfo=timezone.utc)


def simple_workout(kind="easy_run"):
    return Workout.create(id="today", scheduled_for=date(2026, 10, 16),
        workout_type=kind, purpose="Training", planned_duration_minutes=40,
        planned_distance_meters=6000 if kind != "race" else None,
        steps=(WorkoutStep.create(step_type="free_run", duration_seconds=2400,
                                  target=WorkoutTarget.rpe(3)),))


def evidence(*, completed=False, unresolved=False, rest=False):
    return AdviceEvidence(timezone_name="Asia/Taipei", matched_today=completed,
        unresolved_today=unresolved, recovery_label="rest" if rest else "normal",
        recovery_observed_date=date(2026, 10, 16) if rest else None,
        activity_sync_usable=True)


def test_constraints_reject_conflicts_and_range() -> None:
    with pytest.raises(ValueError):
        WorkoutAdviceConstraints(available_minutes=30, cannot_train_today=True)
    with pytest.raises(ValueError):
        WorkoutAdviceConstraints(available_minutes=0)


def test_skip_and_simple_shorten_preserve_target() -> None:
    workout = simple_workout()
    skip = assess_workout_advice(workout=workout, evidence=evidence(),
        constraints=WorkoutAdviceConstraints(cannot_train_today=True), now=TODAY)
    assert skip.mode == "propose_skip_today"
    assert skip.after_workout.status == "skipped"
    assert skip.after_workout.steps == workout.steps
    shorter = assess_workout_advice(workout=workout, evidence=evidence(),
        constraints=WorkoutAdviceConstraints(available_minutes=25), now=TODAY)
    assert shorter.mode == "propose_shorten_easy_run"
    assert shorter.after_workout.planned_duration_minutes == 25
    assert shorter.after_workout.planned_distance_meters is None
    assert shorter.after_workout.steps[0].duration_seconds == 1500
    assert shorter.after_workout.steps[0].target == workout.steps[0].target


def test_completed_uncertain_and_complex_workouts_cannot_be_changed() -> None:
    workout = simple_workout()
    for facts in (evidence(completed=True), evidence(unresolved=True)):
        decision = assess_workout_advice(workout=workout, evidence=facts,
            constraints=WorkoutAdviceConstraints(cannot_train_today=True), now=TODAY)
        assert decision.after_workout is None
    complex_workout = Workout.create(id="complex", scheduled_for=date(2026, 10, 16),
        workout_type="easy_run", purpose="Training", planned_duration_minutes=40,
        steps=(WorkoutStep.create(step_type="warmup", duration_seconds=600),
               WorkoutStep.create(step_type="free_run", duration_seconds=1800)))
    decision = assess_workout_advice(workout=complex_workout, evidence=evidence(),
        constraints=WorkoutAdviceConstraints(available_minutes=25), now=TODAY)
    assert decision.after_workout is None
    assert decision.reason_code == "unsupported_structure"


def test_tiredness_returns_guidance_without_invented_numeric_change() -> None:
    decision = assess_workout_advice(workout=simple_workout(), evidence=evidence(),
        constraints=WorkoutAdviceConstraints(feeling="more_tired"), now=TODAY)
    assert decision.after_workout is None
    assert decision.mode == "no_supported_adjustment"


def test_same_day_recovery_rest_can_propose_skip() -> None:
    decision = assess_workout_advice(workout=simple_workout(), evidence=evidence(rest=True),
        constraints=WorkoutAdviceConstraints(), now=TODAY)
    assert decision.after_workout.status == "skipped"
