from datetime import date, datetime, timezone

from src.domain.training_plan import TrainingPlan, Workout, WorkoutStep, WorkoutTarget
from src.infrastructure.database.coaching_repository import SqlAlchemyCoachingRepository
from src.infrastructure.database.models import Base, UserModel
from src.infrastructure.database.training_plan_repository import SqlAlchemyTrainingPlanRepository
from src.infrastructure.database.uow import SqlAlchemyUnitOfWork


def test_prescription_history_preserves_fields_and_effective_version(sqlite_session_factory) -> None:
    Base.metadata.create_all(sqlite_session_factory.kw["bind"])
    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        user = UserModel(email="history@example.com", display_name="History")
        uow.session.add(user)
        uow.session.flush()
        repository = SqlAlchemyCoachingRepository(uow.session)
        original = Workout.create(
            id="workout-1", scheduled_for=date(2026, 10, 15), workout_type="easy_run",
            purpose="Aerobic", planned_duration_minutes=40, phase="base", coach_note="Keep it easy",
            steps=(WorkoutStep.create(step_type="free_run", duration_seconds=2400, target=WorkoutTarget.rpe(3)),),
        )
        changed = Workout.create(
            id="workout-1", scheduled_for=date(2026, 10, 15), workout_type="easy_run",
            purpose="Aerobic", planned_duration_minutes=30, phase="base", coach_note="Keep it easy",
            steps=(WorkoutStep.create(step_type="free_run", duration_seconds=1800, target=WorkoutTarget.rpe(3)),),
        )
        repository.record_plan_activation(
            user_id=user.id, plan_id="plan-1", effective_at=datetime(2026, 10, 1, tzinfo=timezone.utc),
            effective_local_date=date(2026, 10, 1), timezone_name="Asia/Taipei", previous_plan_id=None,
        )
        original_revision_id = repository.record_prescription_revision(
            user_id=user.id, plan_id="plan-1", workout=original,
            effective_at=datetime(2026, 10, 1, tzinfo=timezone.utc), source="generation",
            confidence="known", recommendation_id=None,
        )
        changed_revision_id = repository.record_prescription_revision(
            user_id=user.id, plan_id="plan-1", workout=changed,
            effective_at=datetime(2026, 10, 15, 8, tzinfo=timezone.utc), source="approved_adjustment",
            confidence="known", recommendation_id="rec-1",
        )
        before = repository.list_prescriptions(
            user.id, date(2026, 10, 15), date(2026, 10, 15), "Asia/Taipei",
            {"workout-1": datetime(2026, 10, 15, 7, tzinfo=timezone.utc)},
        )
        after = repository.list_prescriptions(
            user.id, date(2026, 10, 15), date(2026, 10, 15), "Asia/Taipei", {},
        )
        assert len(before) == len(after) == 1
        assert before[0].workout.to_payload() == original.to_payload()
        assert after[0].workout.to_payload() == changed.to_payload()
        assert before[0].revision_id == original_revision_id
        assert after[0].revision_id == changed_revision_id
        assert before[0].workout.steps[0].target.rpe == 3
        assert after[0].workout.phase == "base"
        uow.commit()


def test_saving_active_plan_records_future_prescription_automatically(sqlite_session_factory) -> None:
    Base.metadata.create_all(sqlite_session_factory.kw["bind"])
    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        user = UserModel(email="automatic-history@example.com", display_name="History")
        uow.session.add(user)
        uow.session.flush()
        workout = Workout.create(
            id="automatic-workout", scheduled_for=date(2027, 1, 5),
            workout_type="easy_run", purpose="Aerobic", planned_duration_minutes=35,
        )
        plan = TrainingPlan.create(
            id="automatic-plan", user_id=user.id, name="Base", starts_on=date(2027, 1, 1),
            ends_on=date(2027, 1, 14), workouts=(workout,),
        )
        SqlAlchemyTrainingPlanRepository(uow.session).save_plan(user.id, plan)
        snapshots = SqlAlchemyCoachingRepository(uow.session).list_prescriptions(
            user.id, date(2027, 1, 5), date(2027, 1, 5), "UTC", {},
        )
        assert len(snapshots) == 1
        assert snapshots[0].workout_id == "automatic-workout"
        assert snapshots[0].workout.planned_duration_minutes == 35
        assert snapshots[0].confidence == "known"
