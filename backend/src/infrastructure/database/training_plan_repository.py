from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from src.domain.training_plan import (
    PlanAdjustmentProposal,
    TrainingPlan,
    Workout,
    WorkoutStep,
    WorkoutTarget,
    validate_phase_segments,
)

from .models import PlanAdjustmentModel, RaceModel, TrainingPlanModel, WorkoutModel


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
            metadata_json={},
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

    def list_active_plans_ending_on_or_before(self, ends_on: date) -> list[TrainingPlan]:
        latest_end_by_user = (
            select(
                TrainingPlanModel.user_id.label("user_id"),
                func.max(TrainingPlanModel.ends_on).label("ends_on"),
            )
            .where(
                TrainingPlanModel.status == "active",
                TrainingPlanModel.ends_on <= ends_on,
            )
            .group_by(TrainingPlanModel.user_id)
            .subquery()
        )
        statement = (
            select(TrainingPlanModel)
            .join(
                latest_end_by_user,
                (TrainingPlanModel.user_id == latest_end_by_user.c.user_id)
                & (TrainingPlanModel.ends_on == latest_end_by_user.c.ends_on),
            )
            .order_by(TrainingPlanModel.user_id, TrainingPlanModel.ends_on.desc(), TrainingPlanModel.id)
        )
        return [_plan_header_from_model(model) for model in self._session.scalars(statement)]

    def list_active_plans_ending_on_or_after(self, ends_on: date) -> list[TrainingPlan]:
        statement = (
            select(TrainingPlanModel)
            .where(
                TrainingPlanModel.status == "active",
                TrainingPlanModel.ends_on >= ends_on,
            )
            .order_by(TrainingPlanModel.user_id, TrainingPlanModel.starts_on, TrainingPlanModel.id)
        )
        return [_plan_header_from_model(model) for model in self._session.scalars(statement)]

    def create_draft_plan(self, user_id: str, plan: TrainingPlan) -> TrainingPlan:
        if plan.status != "draft":
            raise ValueError("draft plan must have draft status")
        return self.save_plan(user_id, plan)

    def create_active_plan(
        self,
        user_id: str,
        plan: TrainingPlan,
        replace_all_active: bool = False,
    ) -> TrainingPlan:
        if plan.status != "active":
            raise ValueError("active plan must have active status")
        validate_phase_segments(plan)
        conflicts = self._active_conflicts_for_plan(user_id, plan, replace_all_active=replace_all_active)
        model = self._save_plan_model(user_id, plan)
        for conflict in conflicts:
            if conflict.id != model.id:
                conflict.status = "superseded"
        self._session.flush()
        return _plan_from_model(model)

    def activate_draft_plan(
        self,
        user_id: str,
        plan_id: str | None,
        *,
        accepted_at: date,
        conflict_created_after: datetime | None = None,
    ) -> TrainingPlan | None:
        if plan_id is None:
            return None
        draft = self._session.scalar(
            select(TrainingPlanModel)
            .options(selectinload(TrainingPlanModel.workouts))
            .where(
                TrainingPlanModel.id == plan_id,
                TrainingPlanModel.user_id == user_id,
                TrainingPlanModel.status == "draft",
            )
        )
        if draft is None:
            return None
        if draft.race_id is not None and self._race_is_expired(draft.race_id, accepted_at):
            return None

        conflicts = self._active_conflicts_for_draft(user_id, draft)
        if conflict_created_after is not None and any(conflict.created_at > conflict_created_after for conflict in conflicts):
            return None
        for conflict in conflicts:
            conflict.status = "superseded"
        draft.status = "active"
        self._session.flush()
        return _plan_from_model(draft)

    def save_plan(self, user_id: str, plan: TrainingPlan) -> TrainingPlan:
        model = self._save_plan_model(user_id, plan)
        self._session.flush()
        return _plan_from_model(model)

    def _save_plan_model(self, user_id: str, plan: TrainingPlan) -> TrainingPlanModel:
        _ensure_matching_user_id(user_id, plan.user_id)
        model = self._get_plan_model(user_id, plan)
        model.user_id = user_id
        model.race_id = plan.race_id
        model.name = plan.name
        model.status = plan.status
        model.starts_on = plan.starts_on
        model.ends_on = plan.ends_on
        model.metadata_json = dict(plan.metadata)
        model.workouts = [_workout_model_from_domain(workout) for workout in plan.workouts]
        return model

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
            metadata_json=dict(plan.metadata),
        )
        self._session.add(model)
        return model

    def _race_is_expired(self, race_id: str, accepted_at: date) -> bool:
        race = self._session.get(RaceModel, race_id)
        return race is not None and race.race_date < accepted_at

    def _active_conflicts_for_draft(self, user_id: str, draft: TrainingPlanModel) -> list[TrainingPlanModel]:
        statement = select(TrainingPlanModel).where(
            TrainingPlanModel.user_id == user_id,
            TrainingPlanModel.id != draft.id,
            TrainingPlanModel.status == "active",
        )
        if draft.race_id is not None:
            statement = statement.where(TrainingPlanModel.race_id == draft.race_id)
        else:
            statement = statement.where(
                TrainingPlanModel.race_id.is_(None),
                TrainingPlanModel.starts_on <= draft.ends_on,
                TrainingPlanModel.ends_on >= draft.starts_on,
            )
        return list(self._session.scalars(statement))

    def _active_conflicts_for_plan(
        self,
        user_id: str,
        plan: TrainingPlan,
        *,
        replace_all_active: bool = False,
    ) -> list[TrainingPlanModel]:
        statement = select(TrainingPlanModel).where(
            TrainingPlanModel.user_id == user_id,
            TrainingPlanModel.status == "active",
        )
        if plan.id is not None:
            statement = statement.where(TrainingPlanModel.id != plan.id)
        if replace_all_active:
            return list(self._session.scalars(statement))
        if plan.race_id is None:
            return []
        statement = statement.where(
            TrainingPlanModel.race_id == plan.race_id,
            TrainingPlanModel.starts_on <= plan.ends_on,
            TrainingPlanModel.ends_on >= plan.starts_on,
        )
        return list(self._session.scalars(statement))


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
        "phase": workout.phase,
        "coach_note": workout.coach_note,
        "steps": [step.to_payload() for step in workout.steps],
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
        metadata=model.metadata_json or {},
        workouts=tuple(_workout_from_model(workout) for workout in model.workouts),
    )


def _plan_header_from_model(model: TrainingPlanModel) -> TrainingPlan:
    return TrainingPlan.create(
        id=model.id,
        user_id=model.user_id,
        race_id=model.race_id,
        name=model.name,
        status=model.status,
        starts_on=model.starts_on,
        ends_on=model.ends_on,
        metadata=model.metadata_json or {},
    )


def _workout_from_model(model: WorkoutModel) -> Workout:
    details = model.details or {}
    pace_range = details.get("pace_range_seconds_per_km")
    steps = tuple(details.get("steps") or ())
    if not steps:
        steps = _synthetic_free_run_steps(model=model, details=details, pace_range=pace_range)
    return Workout.create(
        id=model.id,
        scheduled_for=model.scheduled_for,
        workout_type=model.workout_type,
        purpose=details.get("purpose", model.workout_type),
        planned_duration_minutes=model.planned_duration_minutes,
        planned_distance_meters=details.get("planned_distance_meters"),
        pace_range_seconds_per_km=tuple(pace_range) if pace_range is not None else None,
        heart_rate_zone=details.get("heart_rate_zone"),
        phase=details.get("phase"),
        coach_note=details.get("coach_note"),
        steps=steps,
        status=model.status,
    )


def _synthetic_free_run_steps(*, model: WorkoutModel, details: dict, pace_range) -> tuple[WorkoutStep, ...]:
    duration_seconds = model.planned_duration_minutes * 60 if model.planned_duration_minutes is not None else None
    distance_meters = details.get("planned_distance_meters")
    if duration_seconds is None and distance_meters is None:
        return ()
    target = _synthetic_target(model.workout_type, details=details, pace_range=pace_range)
    return (
        WorkoutStep.create(
            step_type="free_run",
            duration_seconds=duration_seconds,
            distance_meters=distance_meters,
            target=target,
        ),
    )


def _synthetic_target(workout_type: str, *, details: dict, pace_range) -> WorkoutTarget | None:
    if pace_range is not None:
        return WorkoutTarget.pace(
            zone=_pace_zone_for_workout_type(workout_type),
            pace_range_seconds_per_km=tuple(pace_range),
            confidence="low",
        )
    heart_rate_zone = details.get("heart_rate_zone")
    if heart_rate_zone:
        return WorkoutTarget.heart_rate(heart_rate_zone=heart_rate_zone, confidence="low")
    return None


def _pace_zone_for_workout_type(workout_type: str) -> str:
    return {
        "tempo": "threshold",
        "interval": "interval",
        "long_run": "easy",
        "easy_run": "easy",
        "recovery_run": "easy",
    }.get(workout_type, "rpe_only")


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
