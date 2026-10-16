from __future__ import annotations

from fastapi import APIRouter

from src.api.dependencies import CurrentUserDependency, SessionDependency, ensure_current_user
from src.api.errors import ApiForbiddenError, ApiNotFoundError
from src.api.schemas.common import DEFAULT_PAGE_LIMIT, DataEnvelope, ListEnvelope, PageLimit, PageOffset, list_envelope, page_query_limit
from src.api.schemas.training_plans import TrainingPlanRequest, TrainingPlanResponse, WorkoutResponse, WorkoutStatusRequest
from src.domain.training_plan import TrainingPlan, Workout
from src.infrastructure.database.training_plan_repository import SqlAlchemyTrainingPlanRepository


router = APIRouter(prefix="/training-plans", tags=["training-plans"])


@router.post("", response_model=DataEnvelope[TrainingPlanResponse])
def create_training_plan(
    payload: TrainingPlanRequest,
    current_user: CurrentUserDependency,
    session: SessionDependency,
) -> DataEnvelope[TrainingPlanResponse]:
    ensure_current_user(session, current_user)
    plan = _plan_from_request(current_user.id, payload)
    saved = SqlAlchemyTrainingPlanRepository(session).save_plan(current_user.id, plan)
    return DataEnvelope(data=_plan_response(saved))


@router.get("", response_model=ListEnvelope[TrainingPlanResponse])
def list_training_plans(
    current_user: CurrentUserDependency,
    session: SessionDependency,
    limit: PageLimit = DEFAULT_PAGE_LIMIT,
    offset: PageOffset = 0,
) -> ListEnvelope[TrainingPlanResponse]:
    plans = SqlAlchemyTrainingPlanRepository(session).list_plans_for_user(
        current_user.id,
        limit=page_query_limit(limit),
        offset=offset,
    )
    return list_envelope([_plan_response(plan) for plan in plans], limit=limit, offset=offset)


@router.get("/{plan_id}", response_model=DataEnvelope[TrainingPlanResponse])
def get_training_plan(
    plan_id: str,
    current_user: CurrentUserDependency,
    session: SessionDependency,
) -> DataEnvelope[TrainingPlanResponse]:
    plan = SqlAlchemyTrainingPlanRepository(session).get_plan_for_user(current_user.id, plan_id)
    if plan is None:
        raise ApiNotFoundError("training plan not found")
    return DataEnvelope(data=_plan_response(plan))


@router.patch("/{plan_id}/workouts/{workout_id}", response_model=DataEnvelope[TrainingPlanResponse])
def update_workout_status(
    plan_id: str,
    workout_id: str,
    payload: WorkoutStatusRequest,
    current_user: CurrentUserDependency,
    session: SessionDependency,
) -> DataEnvelope[TrainingPlanResponse]:
    repository = SqlAlchemyTrainingPlanRepository(session)
    plan = repository.get_plan_for_user(current_user.id, plan_id)
    if plan is None:
        raise ApiNotFoundError("training plan not found")
    workout = next((item for item in plan.workouts if item.id == workout_id), None)
    if workout is None:
        raise ApiNotFoundError("workout not found")
    if payload.status in {"adjusted", "skipped"}:
        raise ApiForbiddenError("workout_advice_required")
    updated = workout.transition_to(payload.status)
    saved = repository.save_plan(
        current_user.id,
        TrainingPlan.create(
            id=plan.id,
            user_id=plan.user_id,
            race_id=plan.race_id,
            name=plan.name,
            status=plan.status,
            starts_on=plan.starts_on,
            ends_on=plan.ends_on,
            metadata=plan.metadata,
            workouts=tuple(updated if item.id == workout_id else item for item in plan.workouts),
        ),
    )
    return DataEnvelope(data=_plan_response(saved))


def _plan_from_request(user_id: str, payload: TrainingPlanRequest) -> TrainingPlan:
    return TrainingPlan.create(
        user_id=user_id,
        race_id=payload.race_id,
        name=payload.name,
        starts_on=payload.starts_on,
        ends_on=payload.ends_on,
        status=payload.status,
        metadata=payload.metadata,
        workouts=tuple(
            Workout.create(
                scheduled_for=workout.scheduled_for,
                workout_type=workout.workout_type,
                purpose=workout.purpose,
                planned_duration_minutes=workout.planned_duration_minutes,
                planned_distance_meters=workout.planned_distance_meters,
                pace_range_seconds_per_km=tuple(workout.pace_range_seconds_per_km)
                if workout.pace_range_seconds_per_km is not None
                else None,
                heart_rate_zone=workout.heart_rate_zone,
                phase=workout.phase,
                coach_note=workout.coach_note,
                steps=tuple(step.model_dump() for step in workout.steps),
                status=workout.status,
                race_goal_id=workout.race_goal_id,
                race_name=workout.race_name,
                race_priority=workout.race_priority,
            )
            for workout in payload.workouts
        ),
    )


def _plan_response(plan: TrainingPlan) -> TrainingPlanResponse:
    return TrainingPlanResponse(
        id=plan.id,
        user_id=plan.user_id,
        race_id=plan.race_id,
        name=plan.name,
        status=plan.status,
        starts_on=plan.starts_on,
        ends_on=plan.ends_on,
        metadata={key: value for key, value in plan.metadata.items() if key != "internal"},
        preparation_assessment=plan.metadata.get("preparation_assessment") if isinstance(plan.metadata.get("preparation_assessment"), dict) else None,
        workouts=[
            WorkoutResponse(
                id=workout.id,
                scheduled_for=workout.scheduled_for,
                workout_type=workout.workout_type,
                display_name=workout.display_name,
                purpose=workout.purpose,
                planned_duration_minutes=workout.planned_duration_minutes,
                planned_distance_meters=workout.planned_distance_meters,
                pace_range_seconds_per_km=list(workout.pace_range_seconds_per_km)
                if workout.pace_range_seconds_per_km is not None
                else None,
                heart_rate_zone=workout.heart_rate_zone,
                phase=workout.phase,
                coach_note=workout.coach_note,
                steps=[step.to_payload() for step in workout.steps],
                compact_summary=workout.compact_summary,
                status=workout.status,
                race_goal_id=workout.race_goal_id,
                race_name=workout.race_name,
                race_priority=workout.race_priority,
            )
            for workout in plan.workouts
        ],
    )
