from datetime import date, datetime, timezone

from sqlalchemy import select

from scripts.agent_runtime import schedule_once, work_drain
from src.domain.training_plan import Workout
from src.infrastructure.database.coaching_repository import SqlAlchemyCoachingRepository
from src.infrastructure.database.models import AgentTaskModel, AthleteProfileModel, Base, UserModel, RecommendationModel
from src.infrastructure.database.uow import SqlAlchemyUnitOfWork


def test_four_am_schedules_only_closed_day_review_with_historical_prescription(sqlite_session_factory):
    Base.metadata.create_all(sqlite_session_factory.kw["bind"])
    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        user = UserModel(email="schedule-review@example.com", display_name="Runner")
        uow.session.add(user)
        uow.session.flush()
        uow.session.add(AthleteProfileModel(user_id=user.id, timezone="Asia/Taipei"))
        history = SqlAlchemyCoachingRepository(uow.session)
        history.record_plan_activation(user_id=user.id, plan_id="ended-plan",
            effective_at=datetime(2027, 1, 1, tzinfo=timezone.utc),
            effective_local_date=date(2027, 1, 1), timezone_name="Asia/Taipei",
            previous_plan_id=None)
        history.record_prescription_revision(user_id=user.id, plan_id="ended-plan",
            workout=Workout.create(id="yesterday", scheduled_for=date(2027, 1, 15),
                workout_type="easy_run", purpose="Training", planned_duration_minutes=40),
            effective_at=datetime(2027, 1, 1, tzinfo=timezone.utc), source="generation",
            confidence="known", recommendation_id=None)
        assert schedule_once(uow.session, now=datetime(2027, 1, 15, 19, 59, tzinfo=timezone.utc)) == 1
        assert schedule_once(uow.session, now=datetime(2027, 1, 15, 20, tzinfo=timezone.utc)) == 1
        assert schedule_once(uow.session, now=datetime(2027, 1, 15, 20, 1, tzinfo=timezone.utc)) == 0
        tasks = list(uow.session.scalars(select(AgentTaskModel).where(
            AgentTaskModel.task_type == "coaching.sync")))
        assert len(tasks) == 1
        assert tasks[0].payload["workflow_name"] == "daily_review"
        assert tasks[0].payload["input"]["publication_date"] == "2027-01-16"
        assert work_drain(uow.session, max_tasks=3) == 3
        slot = history.get_review_slot(user.id, date(2027, 1, 16))
        assert slot["current"]["kind"] == "daily_review"
        assert uow.session.scalars(select(RecommendationModel).where(RecommendationModel.user_id == user.id)).all() == []
