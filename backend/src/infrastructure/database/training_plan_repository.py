from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from src.domain.training_plan import PlanAdjustmentProposal, TrainingPlan, Workout

from .models import PlanAdjustmentModel, TrainingPlanModel, WorkoutModel


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

    def get_current_plan_for_user(self, user_id: str) -> TrainingPlan | None:
        statement = (
            select(TrainingPlanModel)
            .options(selectinload(TrainingPlanModel.workouts))
            .where(TrainingPlanModel.user_id == user_id, TrainingPlanModel.status == "active")
            .order_by(TrainingPlanModel.starts_on.desc())
            .limit(1)
        )
        model = self._session.scalar(statement)
        if model is None:
            return None
        return _plan_from_model(model)

    def save_plan(self, user_id: str, plan: TrainingPlan) -> TrainingPlan:
        _ensure_matching_user_id(user_id, plan.user_id)
        model = self._get_plan_model(user_id, plan)
        model.user_id = user_id
        model.race_id = plan.race_id
        model.name = plan.name
        model.status = plan.status
        model.starts_on = plan.starts_on
        model.ends_on = plan.ends_on
        model.workouts = [_workout_model_from_domain(workout) for workout in plan.workouts]
        self._session.flush()
        return _plan_from_model(model)

    def get_plan_for_user(self, user_id: str, plan_id: str | None) -> TrainingPlan | None:
        if plan_id is None:
            return None
        model = self._session.scalar(
            select(TrainingPlanModel)
            .options(selectinload(TrainingPlanModel.workouts))
            .where(
                TrainingPlanModel.id == plan_id,
                TrainingPlanModel.user_id == user_id,
            )
        )
        if model is None:
            return None
        return _plan_from_model(model)

    def list_plans_for_user(
        self,
        user_id: str,
        *,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[TrainingPlan]:
        statement = (
            select(TrainingPlanModel)
            .options(selectinload(TrainingPlanModel.workouts))
            .where(TrainingPlanModel.user_id == user_id)
            .order_by(TrainingPlanModel.starts_on.desc(), TrainingPlanModel.id.desc())
        )
        if offset:
            statement = statement.offset(offset)
        if limit is not None:
            statement = statement.limit(limit)
        return [_plan_from_model(model) for model in self._session.scalars(statement)]

    def create_adjustment_proposal(
        self,
        user_id: str,
        proposal: PlanAdjustmentProposal,
    ) -> PlanAdjustmentProposal | None:
        _ensure_matching_user_id(user_id, proposal.user_id)
        plan = self._session.scalar(
            select(TrainingPlanModel).where(
                TrainingPlanModel.id == proposal.training_plan_id,
                TrainingPlanModel.user_id == user_id,
            )
        )
        if plan is None:
            return None
        model = PlanAdjustmentModel(
            training_plan_id=proposal.training_plan_id,
            recommendation_id=proposal.recommendation_id,
            status=proposal.status,
            adjustment_payload=_adjustment_payload(proposal),
        )
        self._session.add(model)
        self._session.flush()
        return _adjustment_from_model(model, user_id=user_id)

    def list_adjustment_proposals_for_plan(
        self,
        user_id: str,
        training_plan_id: str | None,
        *,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[PlanAdjustmentProposal]:
        if training_plan_id is None:
            return []
        plan = self._session.scalar(
            select(TrainingPlanModel).where(
                TrainingPlanModel.id == training_plan_id,
                TrainingPlanModel.user_id == user_id,
            )
        )
        if plan is None:
            return []
        statement = (
            select(PlanAdjustmentModel)
            .where(PlanAdjustmentModel.training_plan_id == training_plan_id)
            .order_by(PlanAdjustmentModel.created_at, PlanAdjustmentModel.id)
        )
        if offset:
            statement = statement.offset(offset)
        if limit is not None:
            statement = statement.limit(limit)
        return [_adjustment_from_model(model, user_id=user_id) for model in self._session.scalars(statement)]

    def _get_plan_model(self, user_id: str, plan: TrainingPlan) -> TrainingPlanModel:
        if plan.id is not None:
            existing = self._session.scalar(
                select(TrainingPlanModel)
                .options(selectinload(TrainingPlanModel.workouts))
                .where(
                    TrainingPlanModel.id == plan.id,
                    TrainingPlanModel.user_id == user_id,
                )
            )
            if existing is not None:
                return existing

        model = TrainingPlanModel(
            user_id=user_id,
            race_id=plan.race_id,
            name=plan.name,
            status=plan.status,
            starts_on=plan.starts_on,
            ends_on=plan.ends_on,
        )
        self._session.add(model)
        return model


def _ensure_matching_user_id(trusted_user_id: str, payload_user_id: str) -> None:
    if trusted_user_id != payload_user_id:
        raise ValueError("payload user_id does not match repository user_id")


def _workout_model_from_domain(workout: Workout) -> WorkoutModel:
    return WorkoutModel(
        id=workout.id,
        scheduled_for=workout.scheduled_for,
        workout_type=workout.workout_type,
        planned_duration_minutes=workout.planned_duration_minutes,
        status=workout.status,
        details=_workout_details(workout),
    )


def _workout_details(workout: Workout) -> dict:
    return {
        "purpose": workout.purpose,
        "planned_distance_meters": workout.planned_distance_meters,
        "pace_range_seconds_per_km": list(workout.pace_range_seconds_per_km)
        if workout.pace_range_seconds_per_km is not None
        else None,
        "heart_rate_zone": workout.heart_rate_zone,
    }


def _plan_from_model(model: TrainingPlanModel) -> TrainingPlan:
    return TrainingPlan.create(
        id=model.id,
        user_id=model.user_id,
        race_id=model.race_id,
        name=model.name,
        status=model.status,
        starts_on=model.starts_on,
        ends_on=model.ends_on,
        workouts=tuple(_workout_from_model(workout) for workout in model.workouts),
    )


def _workout_from_model(model: WorkoutModel) -> Workout:
    details = model.details or {}
    pace_range = details.get("pace_range_seconds_per_km")
    return Workout.create(
        id=model.id,
        scheduled_for=model.scheduled_for,
        workout_type=model.workout_type,
        purpose=details.get("purpose", model.workout_type),
        planned_duration_minutes=model.planned_duration_minutes,
        planned_distance_meters=details.get("planned_distance_meters"),
        pace_range_seconds_per_km=tuple(pace_range) if pace_range is not None else None,
        heart_rate_zone=details.get("heart_rate_zone"),
        status=model.status,
    )


def _adjustment_payload(proposal: PlanAdjustmentProposal) -> dict:
    return {
        "user_id": proposal.user_id,
        "workout_id": proposal.workout_id,
        "before_payload": proposal.before_payload,
        "after_payload": proposal.after_payload,
    }


def _adjustment_from_model(model: PlanAdjustmentModel, *, user_id: str) -> PlanAdjustmentProposal:
    payload = model.adjustment_payload or {}
    return PlanAdjustmentProposal.create(
        id=model.id,
        user_id=user_id,
        training_plan_id=model.training_plan_id,
        workout_id=payload.get("workout_id"),
        recommendation_id=model.recommendation_id,
        before_payload=payload.get("before_payload", {}),
        after_payload=payload.get("after_payload", {}),
        status=model.status,
    )
