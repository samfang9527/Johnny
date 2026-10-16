"""Real two-session races; run with JOHNNY_TEST_DATABASE_URL on disposable PostgreSQL."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import os
from threading import Barrier
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from src.application.coaching_approval import CoachingApprovalService, CoachingDecisionConflict
from src.application.coaching_refresh import CoachingRefreshService
from src.application.workout_advice_generation import GenerateWorkoutAdviceHandler
from src.domain.training_plan import TrainingPlan, Workout, WorkoutStep, WorkoutTarget
from src.domain.workout_advice import WorkoutAdviceConstraints
from src.infrastructure.database.activity_repository import SqlAlchemyActivityRepository
from src.infrastructure.database.coaching_repository import SqlAlchemyCoachingRepository
from src.infrastructure.database.models import ActivityModel, AthleteProfileModel, PlanAdjustmentModel, UserModel
from src.infrastructure.database.training_plan_repository import SqlAlchemyTrainingPlanRepository


@pytest.fixture()
def pg_factory():
    url = os.getenv("JOHNNY_TEST_DATABASE_URL")
    if not url or not url.startswith("postgresql"):
        pytest.skip("disposable PostgreSQL URL not configured")
    engine = create_engine(url, pool_size=4, max_overflow=0)
    try:
        yield sessionmaker(bind=engine, expire_on_commit=False)
    finally:
        engine.dispose()


def _seed_proposal(factory):
    today = datetime.now(timezone.utc).date()
    user_id = str(uuid4())
    workout_id = str(uuid4())
    with factory() as session:
        session.add(UserModel(id=user_id, email=f"{user_id}@example.invalid", display_name="Runner"))
        session.flush()
        session.add(AthleteProfileModel(user_id=user_id, timezone="UTC"))
        plan = TrainingPlan.create(user_id=user_id, name="Concurrency", starts_on=today,
            ends_on=today + timedelta(days=1), workouts=(Workout.create(
                id=workout_id, scheduled_for=today, workout_type="easy_run", purpose="Easy",
                planned_duration_minutes=40, steps=(WorkoutStep.create(
                    step_type="free_run", duration_seconds=2400, target=WorkoutTarget.rpe(3)),)),))
        plans = SqlAlchemyTrainingPlanRepository(session)
        saved = plans.save_plan(user_id, plan)
        result = GenerateWorkoutAdviceHandler(
            coaching=SqlAlchemyCoachingRepository(session), plans=plans,
            activities=SqlAlchemyActivityRepository(session),
        ).handle(user_id=user_id, advice_date=today, timezone_name="UTC",
                 workout_id=workout_id, constraints=WorkoutAdviceConstraints(available_minutes=25),
                 run_id=str(uuid4()), activity_sync_usable=True)
        session.commit()
    return user_id, saved.id, workout_id, result["recommendation_id"]


@pytest.mark.parametrize("second_action", ["accept", "reject"])
def test_competing_decisions_apply_at_most_once(pg_factory, second_action):
    user_id, plan_id, workout_id, proposal_id = _seed_proposal(pg_factory)
    barrier = Barrier(2)

    def decide(action):
        with pg_factory() as session:
            barrier.wait(timeout=5)
            try:
                result = getattr(CoachingApprovalService(session), action)(user_id, proposal_id)
                session.commit()
                return result.decision
            except CoachingDecisionConflict as exc:
                session.rollback()
                return str(exc)

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(decide, "accept")
        second = pool.submit(decide, second_action)
        outcomes = {first.result(timeout=10), second.result(timeout=10)}
    with pg_factory() as session:
        adjustments = session.scalar(select(func.count()).select_from(PlanAdjustmentModel).where(
            PlanAdjustmentModel.recommendation_id == proposal_id))
        current = SqlAlchemyTrainingPlanRepository(session).get_plan_for_date_raw(user_id,
            datetime.now(timezone.utc).date())
        workout = next(item for item in current.workouts if item.id == workout_id)
        if "accepted" in outcomes:
            assert adjustments == 1
            assert workout.planned_duration_minutes == 25
        else:
            assert adjustments == 0
            assert workout.planned_duration_minutes == 40
        assert not ({"accepted", "rejected"} <= outcomes)


def test_competing_review_publications_keep_newest_reservation(pg_factory):
    user_id = str(uuid4())
    today = datetime.now(timezone.utc).date()
    with pg_factory() as session:
        session.add(UserModel(id=user_id, email=f"{user_id}@example.invalid", display_name="Runner"))
        session.flush()
        coaching = SqlAlchemyCoachingRepository(session)
        older = coaching.reserve_review(user_id, today, "UTC", "older-run")
        newer = coaching.reserve_review(user_id, today, "UTC", "newer-run")
        session.commit()
    barrier = Barrier(2)

    def publish(reservation, label):
        with pg_factory() as session:
            barrier.wait(timeout=5)
            result = SqlAlchemyCoachingRepository(session).publish_review(
                reservation, {"narrative": label})
            session.commit()
            return result

    with ThreadPoolExecutor(max_workers=2) as pool:
        old_task = pool.submit(publish, older, "old")
        new_task = pool.submit(publish, newer, "new")
        assert old_task.result(timeout=10) is False
        assert new_task.result(timeout=10) is True
    with pg_factory() as session:
        current = SqlAlchemyCoachingRepository(session).get_review_slot(user_id, today)
        assert current["current"]["narrative"] == "new"


def test_accept_and_activity_import_serialize_without_duplicate_adjustment(pg_factory):
    user_id, _, workout_id, proposal_id = _seed_proposal(pg_factory)
    today = datetime.now(timezone.utc).date()
    barrier = Barrier(2)

    def accept():
        with pg_factory() as session:
            barrier.wait(timeout=5)
            try:
                result = CoachingApprovalService(session).accept(user_id, proposal_id)
                session.commit()
                return result.decision
            except CoachingDecisionConflict:
                session.rollback()
                return "conflict"

    def import_activity():
        with pg_factory() as session:
            barrier.wait(timeout=5)
            session.add(ActivityModel(user_id=user_id, started_at=datetime.now(timezone.utc),
                                      activity_type="running", duration_seconds=1200,
                                      distance_meters=3000))
            session.flush()
            CoachingRefreshService(session).record_change(
                user_id=user_id, changed_dates={today}, today=today, reason="late_activity")
            session.commit()

    with ThreadPoolExecutor(max_workers=2) as pool:
        decision = pool.submit(accept)
        imported = pool.submit(import_activity)
        result = decision.result(timeout=15)
        imported.result(timeout=15)
    with pg_factory() as session:
        adjustments = session.scalar(select(func.count()).select_from(PlanAdjustmentModel).where(
            PlanAdjustmentModel.recommendation_id == proposal_id))
        assert adjustments == (1 if result == "accepted" else 0)
        assert session.scalar(select(func.count()).select_from(ActivityModel).where(
            ActivityModel.user_id == user_id)) == 1
        current = SqlAlchemyTrainingPlanRepository(session).get_plan_for_date_raw(user_id, today)
        workout = next(item for item in current.workouts if item.id == workout_id)
        assert workout.planned_duration_minutes == (25 if result == "accepted" else 40)


def test_accept_and_plan_activation_serialize_to_one_current_plan(pg_factory):
    user_id, original_plan_id, _, proposal_id = _seed_proposal(pg_factory)
    today = datetime.now(timezone.utc).date()
    replacement = TrainingPlan.create(
        user_id=user_id, name="Replacement", starts_on=today,
        ends_on=today + timedelta(days=1), metadata={"phase_segments": [{
            "phase": "maintenance", "starts_on": today.isoformat(),
            "ends_on": (today + timedelta(days=1)).isoformat(),
        }]}, workouts=(Workout.create(
            id=str(uuid4()), scheduled_for=today, workout_type="easy_run", purpose="Replacement",
            planned_duration_minutes=30, phase="maintenance", steps=(WorkoutStep.create(
                step_type="free_run", duration_seconds=1800, target=WorkoutTarget.rpe(3)),)),),
    )
    barrier = Barrier(2)

    def accept():
        with pg_factory() as session:
            barrier.wait(timeout=5)
            try:
                result = CoachingApprovalService(session).accept(user_id, proposal_id)
                session.commit()
                return result.decision
            except CoachingDecisionConflict:
                session.rollback()
                return "conflict"

    def activate():
        with pg_factory() as session:
            barrier.wait(timeout=5)
            created = SqlAlchemyTrainingPlanRepository(session).create_active_plan(
                user_id, replacement, replace_all_active=True)
            session.commit()
            return created.id

    with ThreadPoolExecutor(max_workers=2) as pool:
        decision = pool.submit(accept)
        activated = pool.submit(activate)
        result = decision.result(timeout=15)
        replacement_id = activated.result(timeout=15)
    with pg_factory() as session:
        current = SqlAlchemyTrainingPlanRepository(session).get_plan_for_date_raw(user_id, today)
        assert current.id == replacement_id
        assert session.scalar(select(func.count()).select_from(PlanAdjustmentModel).where(
            PlanAdjustmentModel.recommendation_id == proposal_id)) == (1 if result == "accepted" else 0)
        assert current.id != original_plan_id
