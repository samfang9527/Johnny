from __future__ import annotations

from datetime import date

from fastapi import APIRouter

from src.api.dependencies import CurrentUserDependency, SessionDependency, ensure_current_user
from src.api.regeneration_composition import (
    RegenerationOptionsHandlerDependency,
    StartRegenerationHandlerDependency,
)
from src.api.schemas.common import DataEnvelope
from src.api.schemas.training_plan_regeneration import (
    RegenerationQuotaResponse,
    RegenerationRunResponse,
    RegenerationStrategyResponse,
    TrainingPlanRegenerationRequest,
    TrainingPlanRegenerationResponse,
)
from src.application.training_plan_regeneration import RegenerationRequest


router = APIRouter(prefix="/training-plans", tags=["training-plans"])


@router.get("/regeneration-options", response_model=DataEnvelope[TrainingPlanRegenerationResponse])
def get_regeneration_options(
    current_user: CurrentUserDependency,
    session: SessionDependency,
    handler: RegenerationOptionsHandlerDependency,
) -> DataEnvelope[TrainingPlanRegenerationResponse]:
    ensure_current_user(session, current_user)
    result = handler.handle(user_id=current_user.id, today=date.today())
    return DataEnvelope(data=_response(result))


@router.post("/regenerations", response_model=DataEnvelope[TrainingPlanRegenerationResponse])
def start_regeneration(
    payload: TrainingPlanRegenerationRequest,
    current_user: CurrentUserDependency,
    session: SessionDependency,
    handler: StartRegenerationHandlerDependency,
) -> DataEnvelope[TrainingPlanRegenerationResponse]:
    ensure_current_user(session, current_user)
    request = RegenerationRequest(
        client_request_id=payload.client_request_id,
        plan_type=payload.plan_type,
        race_id=payload.race_id,
    )
    result = handler.handle(user_id=current_user.id, request=request, today=date.today())
    return DataEnvelope(data=_response(result))


def _response(result) -> TrainingPlanRegenerationResponse:
    return TrainingPlanRegenerationResponse(
        quota=RegenerationQuotaResponse(
            quota_day=result.quota.quota_day,
            limit=result.quota.limit,
            used=result.quota.used,
            remaining=result.quota.remaining,
            available=result.quota.available,
            next_available_at=result.quota.next_available_at,
        ),
        default_strategy=RegenerationStrategyResponse(
            race_id=result.default_strategy.race_id,
            plan_type=result.default_strategy.plan_type,
            reason=result.default_strategy.reason,
            starts_on=result.default_strategy.starts_on,
            plan_horizon_weeks=result.default_strategy.plan_horizon_weeks,
        ),
        in_flight_run=_run_response(result.in_flight_run),
        run=_run_response(result.run),
    )


def _run_response(run) -> RegenerationRunResponse | None:
    if run is None:
        return None
    return RegenerationRunResponse(
        run_id=run.run_id,
        status=run.status,
        workflow_name=run.workflow_name,
        poll_url=run.poll_url,
    )
