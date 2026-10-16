from datetime import date, datetime, timezone

from src.application.workout_advice_generation import GenerateWorkoutAdviceHandler
from src.application.coaching_approval import CoachingApprovalService
from src.domain.training_plan import TrainingPlan, Workout, WorkoutStep, WorkoutTarget
from src.domain.workout_advice import WorkoutAdviceConstraints
from src.infrastructure.database.activity_repository import SqlAlchemyActivityRepository
from src.infrastructure.database.coaching_repository import SqlAlchemyCoachingRepository
from src.infrastructure.database.models import AthleteProfileModel, Base, UserModel
from src.infrastructure.database.training_plan_repository import SqlAlchemyTrainingPlanRepository
from src.infrastructure.database.uow import SqlAlchemyUnitOfWork


def test_requested_advice_creates_proposal_but_keeps_plan_unchanged(sqlite_session_factory):
    Base.metadata.create_all(sqlite_session_factory.kw["bind"])
    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        user = UserModel(email="advice-flow@example.com", display_name="Runner")
        uow.session.add(user)
        uow.session.flush()
        uow.session.add(AthleteProfileModel(user_id=user.id, timezone="Asia/Taipei"))
        plans = SqlAlchemyTrainingPlanRepository(uow.session)
        original = Workout.create(id="today-run", scheduled_for=date(2027, 1, 16),
            workout_type="easy_run", purpose="Training", planned_duration_minutes=40,
            steps=(WorkoutStep.create(step_type="free_run", duration_seconds=2400,
                target=WorkoutTarget.rpe(3)),))
        plans.save_plan(user.id, TrainingPlan.create(user_id=user.id, name="Base",
            starts_on=date(2027, 1, 1), ends_on=date(2027, 1, 31), workouts=(original,)))
        coaching = SqlAlchemyCoachingRepository(uow.session)
        result = GenerateWorkoutAdviceHandler(coaching=coaching, plans=plans,
            activities=SqlAlchemyActivityRepository(uow.session),
            now=lambda: datetime(2027, 1, 16, 1, tzinfo=timezone.utc)).handle(
            user_id=user.id, advice_date=date(2027, 1, 16), timezone_name="Asia/Taipei",
            workout_id="today-run", constraints=WorkoutAdviceConstraints(available_minutes=25),
            run_id="advice-run", activity_sync_usable=True)
        assert result["mode"] == "propose_shorten_easy_run"
        assert result["recommendation_id"]
        assert result["after"]["planned_duration_minutes"] == 25
        assert plans.get_current_plan_for_user(user.id).workouts[0].planned_duration_minutes == 40
        approval = CoachingApprovalService(uow.session, now=lambda: datetime(2027, 1, 16, 1, 5, tzinfo=timezone.utc))
        accepted = approval.accept(user.id, result["recommendation_id"])
        assert accepted.decision == "accepted"
        assert approval.accept(user.id, result["recommendation_id"]).id == accepted.id
        applied = plans.get_plan_for_date_raw(user.id, date(2027, 1, 16)).workouts[0]
        assert applied.planned_duration_minutes == 25
        assert applied.steps[0].target.rpe == 3


def test_rejected_identical_adjustment_is_not_proposed_again(sqlite_session_factory):
    Base.metadata.create_all(sqlite_session_factory.kw["bind"])
    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        user = UserModel(email="declined-advice@example.com", display_name="Runner")
        uow.session.add(user)
        uow.session.flush()
        uow.session.add(AthleteProfileModel(user_id=user.id, timezone="UTC"))
        plans = SqlAlchemyTrainingPlanRepository(uow.session)
        workout = Workout.create(id="declined-run", scheduled_for=date(2027, 1, 16),
            workout_type="easy_run", purpose="Easy", planned_duration_minutes=40,
            steps=(WorkoutStep.create(step_type="free_run", duration_seconds=2400,
                target=WorkoutTarget.rpe(3)),))
        plans.save_plan(user.id, TrainingPlan.create(user_id=user.id, name="Base",
            starts_on=date(2027, 1, 16), ends_on=date(2027, 1, 17), workouts=(workout,)))
        coaching = SqlAlchemyCoachingRepository(uow.session)
        handler = GenerateWorkoutAdviceHandler(coaching=coaching, plans=plans,
            activities=SqlAlchemyActivityRepository(uow.session),
            now=lambda: datetime(2027, 1, 16, 8, tzinfo=timezone.utc))
        inputs = dict(user_id=user.id, advice_date=date(2027, 1, 16), timezone_name="UTC",
                      workout_id="declined-run", constraints=WorkoutAdviceConstraints(available_minutes=25),
                      activity_sync_usable=True)
        first = handler.handle(**inputs, run_id="first-declined-advice")
        CoachingApprovalService(uow.session).reject(user.id, first["recommendation_id"])
        second = handler.handle(**inputs, run_id="second-declined-advice")
        assert second["mode"] == "previously_declined"
        assert second.get("recommendation_id") is None
        assert second["decision_fingerprint"] == first["decision_fingerprint"]
        assert plans.get_plan_for_date_raw(user.id, date(2027, 1, 16)).workouts[0].planned_duration_minutes == 40
