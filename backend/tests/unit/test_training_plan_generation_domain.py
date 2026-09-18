from datetime import date

import pytest

from src.domain.training_plan import (
    DomainValidationError,
    TrainingPlan,
    Workout,
    is_hard_session,
    validate_phase_segments,
)


def _workout(*, scheduled_for: date, phase: str | None = "base", workout_type: str = "easy_run") -> Workout:
    return Workout.create(
        scheduled_for=scheduled_for,
        workout_type=workout_type,
        purpose="Build aerobic consistency",
        planned_duration_minutes=45,
        phase=phase,
    )


def _plan(*, segments: list[dict], workouts: tuple[Workout, ...] = ()) -> TrainingPlan:
    return TrainingPlan.create(
        user_id="user-1",
        name="Generated Plan",
        starts_on=date(2027, 1, 1),
        ends_on=date(2027, 1, 7),
        metadata={"phase_segments": segments},
        workouts=workouts,
    )


def test_validate_phase_segments_accepts_continuous_inclusive_segments() -> None:
    plan = _plan(
        segments=[
            {"phase": "base", "starts_on": "2027-01-01", "ends_on": "2027-01-03"},
            {"phase": "build", "starts_on": "2027-01-04", "ends_on": "2027-01-07"},
        ],
        workouts=(
            _workout(scheduled_for=date(2027, 1, 3), phase="base"),
            _workout(scheduled_for=date(2027, 1, 4), phase="build"),
        ),
    )

    validate_phase_segments(plan)


def test_validate_phase_segments_rejects_a_gap() -> None:
    plan = _plan(
        segments=[
            {"phase": "base", "starts_on": "2027-01-01", "ends_on": "2027-01-03"},
            {"phase": "build", "starts_on": "2027-01-05", "ends_on": "2027-01-07"},
        ]
    )

    with pytest.raises(DomainValidationError, match="phase segments do not fully cover plan date range"):
        validate_phase_segments(plan)


def test_validate_phase_segments_rejects_an_overlap() -> None:
    plan = _plan(
        segments=[
            {"phase": "base", "starts_on": "2027-01-01", "ends_on": "2027-01-04"},
            {"phase": "build", "starts_on": "2027-01-04", "ends_on": "2027-01-07"},
        ]
    )

    with pytest.raises(DomainValidationError, match="phase segments overlap"):
        validate_phase_segments(plan)


def test_validate_phase_segments_rejects_a_workout_phase_mismatch() -> None:
    plan = _plan(
        segments=[{"phase": "base", "starts_on": "2027-01-01", "ends_on": "2027-01-07"}],
        workouts=(_workout(scheduled_for=date(2027, 1, 3), phase="build"),),
    )

    with pytest.raises(DomainValidationError, match="workout phase does not match phase segment"):
        validate_phase_segments(plan)


def test_validate_phase_segments_rejects_a_missing_workout_phase() -> None:
    plan = _plan(
        segments=[{"phase": "base", "starts_on": "2027-01-01", "ends_on": "2027-01-07"}],
        workouts=(_workout(scheduled_for=date(2027, 1, 3), phase=None),),
    )

    with pytest.raises(DomainValidationError, match="workout phase is required"):
        validate_phase_segments(plan)


def test_workout_rejects_an_unsupported_phase() -> None:
    with pytest.raises(DomainValidationError, match="workout phase is not supported"):
        _workout(scheduled_for=date(2027, 1, 3), phase="unsupported")


def test_hill_workouts_are_supported_hard_sessions() -> None:
    hill_workout = _workout(scheduled_for=date(2027, 1, 3), workout_type="hill")

    assert is_hard_session(hill_workout) is True
