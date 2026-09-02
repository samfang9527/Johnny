from datetime import date

import pytest

from src.domain.training_plan import (
    DomainValidationError,
    PlanAdjustmentProposal,
    TrainingPlan,
    Workout,
)


def _easy_workout(*, scheduled_for: date = date(2027, 1, 3), id: str | None = None) -> Workout:
    return Workout.create(
        id=id,
        scheduled_for=scheduled_for,
        workout_type="easy_run",
        purpose="Aerobic base",
        planned_duration_minutes=45,
        planned_distance_meters=8_000,
        pace_range_seconds_per_km=(330, 390),
        heart_rate_zone="z2",
    )


def test_manual_training_plan_orders_workouts_and_validates_boundaries() -> None:
    later = _easy_workout(scheduled_for=date(2027, 1, 5))
    earlier = _easy_workout(scheduled_for=date(2027, 1, 3))

    plan = TrainingPlan.create(
        user_id="user-1",
        race_id="race-1",
        name="Half Marathon Build",
        starts_on=date(2027, 1, 1),
        ends_on=date(2027, 3, 1),
        workouts=(later, earlier),
    )

    assert plan.user_id == "user-1"
    assert plan.race_id == "race-1"
    assert plan.status == "active"
    assert [workout.scheduled_for for workout in plan.workouts] == [date(2027, 1, 3), date(2027, 1, 5)]


def test_generated_training_plan_can_remain_draft_or_be_superseded() -> None:
    draft = TrainingPlan.create(
        user_id="user-1",
        race_id="race-1",
        name="Generated Half Marathon Draft",
        starts_on=date(2027, 1, 1),
        ends_on=date(2027, 1, 31),
        status="draft",
        workouts=(_easy_workout(scheduled_for=date(2027, 1, 3)),),
    )
    superseded = TrainingPlan.create(
        user_id="user-1",
        race_id="race-1",
        name="Older Half Marathon Plan",
        starts_on=date(2027, 1, 1),
        ends_on=date(2027, 1, 31),
        status="superseded",
        workouts=(_easy_workout(scheduled_for=date(2027, 1, 3)),),
    )

    assert draft.status == "draft"
    assert superseded.status == "superseded"


def test_training_plan_rejects_invalid_date_range() -> None:
    with pytest.raises(DomainValidationError, match="end date"):
        TrainingPlan.create(
            user_id="user-1",
            name="Invalid Plan",
            starts_on=date(2027, 3, 1),
            ends_on=date(2027, 1, 1),
        )


def test_training_plan_rejects_workouts_outside_plan_boundaries() -> None:
    with pytest.raises(DomainValidationError, match="outside plan date range"):
        TrainingPlan.create(
            user_id="user-1",
            name="Invalid Plan",
            starts_on=date(2027, 1, 1),
            ends_on=date(2027, 1, 31),
            workouts=(_easy_workout(scheduled_for=date(2027, 2, 1)),),
        )


def test_workout_accepts_supported_details() -> None:
    workout = _easy_workout()

    assert workout.workout_type == "easy_run"
    assert workout.purpose == "Aerobic base"
    assert workout.planned_duration_minutes == 45
    assert workout.planned_distance_meters == 8_000
    assert workout.pace_range_seconds_per_km == (330, 390)
    assert workout.heart_rate_zone == "z2"
    assert workout.status == "planned"


def test_workout_rejects_unsupported_type() -> None:
    with pytest.raises(DomainValidationError, match="workout type"):
        Workout.create(
            scheduled_for=date(2027, 1, 3),
            workout_type="unsupported",
            purpose="Bad workout",
            planned_duration_minutes=45,
        )


def test_workout_rejects_missing_planned_load() -> None:
    with pytest.raises(DomainValidationError, match="planned distance or duration"):
        Workout.create(
            scheduled_for=date(2027, 1, 3),
            workout_type="easy_run",
            purpose="Missing load",
        )


def test_workout_status_transitions_preserve_planned_details() -> None:
    planned = _easy_workout(id="workout-1")
    completed = planned.transition_to("completed")

    assert completed.id == "workout-1"
    assert completed.status == "completed"
    assert completed.planned_duration_minutes == planned.planned_duration_minutes
    assert completed.planned_distance_meters == planned.planned_distance_meters


def test_workout_rejects_invalid_status_transition() -> None:
    completed = _easy_workout().transition_to("completed")

    with pytest.raises(DomainValidationError, match="status transition"):
        completed.transition_to("planned")


def test_adjustment_proposal_preserves_before_and_after_without_mutating_workout() -> None:
    workout = _easy_workout(id="workout-1")
    before_payload = workout.to_payload()
    after_payload = {**before_payload, "planned_duration_minutes": 30}

    proposal = PlanAdjustmentProposal.create(
        user_id="user-1",
        training_plan_id="plan-1",
        workout_id=workout.id,
        before_payload=before_payload,
        after_payload=after_payload,
        recommendation_id="recommendation-1",
    )

    assert proposal.status == "proposed"
    assert proposal.before_payload["planned_duration_minutes"] == 45
    assert proposal.after_payload["planned_duration_minutes"] == 30
    assert workout.planned_duration_minutes == 45


def test_adjustment_proposal_status_transitions() -> None:
    proposal = PlanAdjustmentProposal.create(
        user_id="user-1",
        training_plan_id="plan-1",
        before_payload={"planned_duration_minutes": 45},
        after_payload={"planned_duration_minutes": 30},
    )

    approved = proposal.transition_to("approved")
    applied = approved.transition_to("applied")
    rejected = proposal.transition_to("rejected")

    assert approved.status == "approved"
    assert applied.status == "applied"
    assert rejected.status == "rejected"


def test_adjustment_proposal_rejects_invalid_transition() -> None:
    rejected = PlanAdjustmentProposal.create(
        user_id="user-1",
        training_plan_id="plan-1",
        before_payload={"planned_duration_minutes": 45},
        after_payload={"planned_duration_minutes": 30},
    ).transition_to("rejected")

    with pytest.raises(DomainValidationError, match="proposal status transition"):
        rejected.transition_to("applied")
