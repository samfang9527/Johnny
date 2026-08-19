from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from .models import TrainingPlanModel, WorkoutModel


class SqlAlchemyTrainingPlanRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create_plan(
        self,
        *,
        user_id: str,
        race_id: str | None,
        name: str,
        starts_on: date,
        ends_on: date,
    ) -> TrainingPlanModel:
        plan = TrainingPlanModel(
            user_id=user_id,
            race_id=race_id,
            name=name,
            starts_on=starts_on,
            ends_on=ends_on,
        )
        self._session.add(plan)
        self._session.flush()
        return plan

    def add_workout(
        self,
        *,
        training_plan_id: str,
        scheduled_for: date,
        workout_type: str,
        planned_duration_minutes: int | None = None,
    ) -> WorkoutModel:
        workout = WorkoutModel(
            training_plan_id=training_plan_id,
            scheduled_for=scheduled_for,
            workout_type=workout_type,
            planned_duration_minutes=planned_duration_minutes,
        )
        self._session.add(workout)
        self._session.flush()
        return workout

    def get_current_plan_for_user(self, user_id: str) -> TrainingPlanModel | None:
        statement = (
            select(TrainingPlanModel)
            .options(selectinload(TrainingPlanModel.workouts))
            .where(TrainingPlanModel.user_id == user_id, TrainingPlanModel.status == "active")
            .order_by(TrainingPlanModel.starts_on.desc())
            .limit(1)
        )
        return self._session.scalar(statement)
