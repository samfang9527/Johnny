from datetime import date, datetime, timezone

import pytest

from src.application.coaching_approval import CoachingApprovalService, CoachingDecisionConflict
from src.application.workout_advice_generation import GenerateWorkoutAdviceHandler
from src.domain.activity_health import DailyHealthMetrics
from src.domain.training_plan import TrainingPlan, Workout, WorkoutStep, WorkoutTarget
from src.domain.workout_advice import WorkoutAdviceConstraints
from src.infrastructure.database.activity_repository import SqlAlchemyActivityRepository
from src.infrastructure.database.coaching_repository import SqlAlchemyCoachingRepository
from src.infrastructure.database.models import Base, UserModel
from src.infrastructure.database.training_plan_repository import SqlAlchemyTrainingPlanRepository


# Taipei is already Jan 16 while UTC is still Jan 15.
NOW = datetime(2027, 1, 15, 23, tzinfo=timezone.utc)
TODAY = date(2027, 1, 16)
YESTERDAY = date(2027, 1, 15)
REST = dict(sleep_duration_minutes=300, hrv_ms=35, hrv_baseline_ms=50,
            stress_score=75, body_battery_score=20)
READY = dict(sleep_duration_minutes=480, hrv_ms=50, hrv_baseline_ms=50,
             stress_score=20, body_battery_score=80)


@pytest.fixture
def recovery_advice(sqlite_session_factory):
    Base.metadata.create_all(sqlite_session_factory.kw["bind"])
    with sqlite_session_factory() as session:
        session.add(UserModel(id="recovery-athlete", email="recovery@example.test", display_name="Runner"))
        session.flush()
        plans = SqlAlchemyTrainingPlanRepository(session)
        workout = Workout.create(id="recovery-workout", scheduled_for=TODAY,
            workout_type="easy_run", purpose="Easy", planned_duration_minutes=40,
            steps=(WorkoutStep.create(step_type="free_run", duration_seconds=2400,
                                      target=WorkoutTarget.rpe(3)),))
        plans.save_plan("recovery-athlete", TrainingPlan.create(user_id="recovery-athlete", name="Base",
            starts_on=TODAY, ends_on=TODAY, workouts=(workout,)))
        activities = SqlAlchemyActivityRepository(session)
        handler = GenerateWorkoutAdviceHandler(coaching=SqlAlchemyCoachingRepository(session),
            plans=plans, activities=activities, now=lambda: NOW)

        def save(day, values, user_id="recovery-athlete"):
            activities.save_daily_health_metrics(user_id, DailyHealthMetrics.create(
                user_id=user_id, metric_date=day, **values))

        def generate(run_id="recovery-run", **constraints):
            return handler.handle(user_id="recovery-athlete", advice_date=TODAY,
                timezone_name="Asia/Taipei", workout_id="recovery-workout",
                constraints=WorkoutAdviceConstraints(**constraints), run_id=run_id,
                activity_sync_usable=True)

        yield session, plans, save, generate


def test_today_recovery_proposes_skip_with_evidence_and_requires_acceptance(recovery_advice):
    session, plans, save, generate = recovery_advice
    save(YESTERDAY, READY)
    save(TODAY, REST)
    result = generate()
    assert result["reason_code"] == "same_day_recovery_rest"
    assert result["after"]["status"] == "skipped"
    assert result["recovery"]["observed_date"] == "2027-01-16"
    assert result["recovery"]["days"][1]["signals"]["hrv"]["baseline"] == 50
    assert all(label in result["guidance"] for label in ("睡眠", "HRV", "壓力", "Body Battery"))
    assert plans.get_plan_for_date_raw("recovery-athlete", TODAY).workouts[0].status == "planned"
    accepted = CoachingApprovalService(session, now=lambda: NOW).accept(
        "recovery-athlete", result["recommendation_id"])
    assert accepted.decision == "accepted"
    assert plans.get_plan_for_date_raw("recovery-athlete", TODAY).workouts[0].status == "skipped"


def test_yesterday_recovery_informs_guidance_without_becoming_today_evidence(recovery_advice):
    _, _, save, generate = recovery_advice
    save(YESTERDAY, REST)
    result = generate()
    assert result["reason_code"] == "previous_day_recovery_rest"
    assert result["recovery"]["observed_date"] == "2027-01-15"
    assert result["recovery"]["readiness_label"] == "rest"
    assert "2027-01-15" in result["guidance"]
    assert "昨天" in result["guidance"]
    assert result.get("recommendation_id") is None
    assert result["after"] is None


def test_latest_recovery_takes_precedence_but_keeps_yesterday_context(recovery_advice):
    _, _, save, generate = recovery_advice
    save(YESTERDAY, REST)
    save(TODAY, READY)
    result = generate()
    assert result["reason_code"] == "follow_plan"
    assert result["recovery"]["readiness_label"] == "ready"
    assert result["recovery"]["observed_date"] == "2027-01-16"
    assert [day["readiness_label"] for day in result["recovery"]["days"]] == ["rest", "ready"]
    assert "2027-01-15" in result["guidance"] and "2027-01-16" in result["guidance"]


@pytest.mark.parametrize("values", [dict(stress_score=80),
    dict(hrv_ms=35, hrv_baseline_ms=0), dict(sleep_quality=90),
    dict(resting_heart_rate=55), dict(hrv_baseline_ms=0)])
def test_insufficient_today_signals_are_not_replaced_with_yesterday_readiness(recovery_advice, values):
    _, _, save, generate = recovery_advice
    save(YESTERDAY, READY)
    save(TODAY, values)
    result = generate()
    assert result["recovery"]["readiness_label"] == "unknown"
    assert result["reason_code"] == "recovery_unavailable"
    assert "不足" in result["guidance"]
    assert result["recovery"]["days"][1]["missing_signals"]
    assert result.get("recommendation_id") is None


def test_old_future_and_other_athlete_health_do_not_supply_recovery(recovery_advice):
    session, _, save, generate = recovery_advice
    session.add(UserModel(id="other", email="other@example.test", display_name="Other"))
    session.flush()
    save(date(2027, 1, 14), REST)
    save(date(2027, 1, 17), REST)
    save(TODAY, REST, "other")
    result = generate()
    assert result["reason_code"] == "recovery_unavailable"
    assert result["recovery"]["observed_date"] is None
    assert all(not day["signals"] for day in result["recovery"]["days"])
    assert result.get("recommendation_id") is None


def test_health_changes_affect_evidence_fingerprint_and_block_stale_acceptance(recovery_advice):
    session, plans, save, generate = recovery_advice
    save(TODAY, REST)
    first = generate("first")
    unchanged = generate("same-evidence")
    assert first["evidence_fingerprint"] == unchanged["evidence_fingerprint"]
    save(TODAY, READY)
    with pytest.raises(CoachingDecisionConflict, match="recovery_evidence_changed"):
        CoachingApprovalService(session, now=lambda: NOW).accept(
            "recovery-athlete", unchanged["recommendation_id"])
    assert plans.get_plan_for_date_raw("recovery-athlete", TODAY).workouts[0].status == "planned"
    refreshed = generate("updated")
    assert refreshed["evidence_fingerprint"] != first["evidence_fingerprint"]
    assert refreshed["reason_code"] == "follow_plan"


def test_caution_gives_guidance_without_inventing_workout_changes(recovery_advice):
    _, _, save, generate = recovery_advice
    save(TODAY, {**READY, "stress_score": 55})
    result = generate()
    assert result["reason_code"] == "recovery_caution"
    assert result["recovery"]["readiness_label"] == "caution"
    assert result["after"] is None
