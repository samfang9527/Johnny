from datetime import date

import pytest

from src.domain.training_plan import (
    DomainValidationError,
    PlanAdjustmentProposal,
    TrainingPlan,
    Workout,
    WorkoutStep,
    WorkoutTarget,
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


def test_interval_workout_accepts_repeat_steps_and_derives_compact_summary() -> None:
    workout = Workout.create(
        scheduled_for=date(2027, 1, 5),
        workout_type="interval",
        purpose="Improve 5K-specific aerobic power",
        planned_duration_minutes=55,
        planned_distance_meters=8_600,
        phase="build",
        coach_note="Keep the first two reps controlled.",
        steps=(
            WorkoutStep.create(
                step_type="warmup",
                duration_seconds=900,
                target=WorkoutTarget.rpe(3),
            ),
            WorkoutStep.create(
                step_type="repeat",
                repeat_count=4,
                steps=(
                    WorkoutStep.create(
                        step_type="work",
                        distance_meters=800,
                        target=WorkoutTarget.pace(zone="interval", pace_range_seconds_per_km=(275, 285), rpe=8),
                    ),
                    WorkoutStep.create(
                        step_type="recovery",
                        distance_meters=400,
                        target=WorkoutTarget.pace(zone="easy", rpe=3),
                    ),
                ),
            ),
            WorkoutStep.create(
                step_type="cooldown",
                duration_seconds=600,
                target=WorkoutTarget.rpe(2),
            ),
        ),
    )

    assert workout.phase == "build"
    assert workout.coach_note == "Keep the first two reps controlled."
    assert workout.display_name == "間歇跑 · 4 組 × 800 公尺"
    assert workout.compact_summary == "暖身 15 分鐘 ＋ 4 組（主課表・間歇配速 800 公尺／組間恢復・輕鬆配速 400 公尺） ＋ 緩和 10 分鐘"
    assert workout.to_payload()["steps"][1]["repeat_count"] == 4


def test_workout_steps_reject_missing_load_and_bad_repeat_blocks() -> None:
    with pytest.raises(DomainValidationError, match="step requires distance or duration"):
        WorkoutStep.create(step_type="work", target=WorkoutTarget.rpe(6))

    with pytest.raises(DomainValidationError, match="repeat block requires nested steps"):
        WorkoutStep.create(step_type="repeat", repeat_count=4, steps=())


def test_workout_rejects_step_totals_outside_tolerance_and_long_coach_note() -> None:
    with pytest.raises(DomainValidationError, match="planned duration does not match workout steps"):
        Workout.create(
            scheduled_for=date(2027, 1, 5),
            workout_type="tempo",
            purpose="Threshold development",
            planned_duration_minutes=30,
            steps=(WorkoutStep.create(step_type="warmup", duration_seconds=2_400, target=WorkoutTarget.rpe(3)),),
        )

    with pytest.raises(DomainValidationError, match="coach note"):
        Workout.create(
            scheduled_for=date(2027, 1, 5),
            workout_type="easy_run",
            purpose="Aerobic base",
            planned_duration_minutes=45,
            coach_note="x" * 501,
        )


def test_workout_can_derive_planned_load_from_steps() -> None:
    workout = Workout.create(
        scheduled_for=date(2027, 1, 5),
        workout_type="tempo",
        purpose="Threshold development",
        steps=(
            WorkoutStep.create(step_type="warmup", duration_seconds=600, target=WorkoutTarget.rpe(3)),
            WorkoutStep.create(step_type="work", duration_seconds=1_800, target=WorkoutTarget.pace(zone="threshold")),
            WorkoutStep.create(step_type="cooldown", duration_seconds=600, target=WorkoutTarget.rpe(2)),
        ),
    )

    assert workout.planned_duration_minutes == 50
    assert workout.planned_distance_meters is None


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
