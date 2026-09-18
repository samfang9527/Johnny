from __future__ import annotations

from datetime import date

from fastapi import APIRouter
from sqlalchemy import select

from src.api.dependencies import CurrentUserDependency, SessionDependency, ensure_current_user
from src.api.schemas.common import DataEnvelope
from src.api.schemas.training_plan_regeneration import (
    RegenerationQuotaResponse,
    RegenerationRunResponse,
    RegenerationStrategyResponse,
    TrainingPlanRegenerationRequest,
    TrainingPlanRegenerationResponse,
)
from src.application.async_agent_runs import QueueAgentRunHandler
from src.application.training_plan_regeneration import TrainingPlanRegenerationService
from src.infrastructure.database.agent_run_repository import SqlAlchemyAgentRunRepository
from src.infrastructure.database.agent_task_queue import SqlAlchemyAgentTaskQueue
from src.infrastructure.database.athlete_race_repository import SqlAlchemyAthleteRaceRepository
from src.infrastructure.database.models import UserModel


router = APIRouter(prefix="/training-plans", tags=["training-plans"])


@router.get("/regeneration-options", response_model=DataEnvelope[TrainingPlanRegenerationResponse])
def get_regeneration_options(
    current_user: CurrentUserDependency,
    session: SessionDependency,
) -> DataEnvelope[TrainingPlanRegenerationResponse]:
    ensure_current_user(session, current_user)
    result = _service(session).options(current_user.id, date.today())
    return DataEnvelope(data=_response(result))


@router.post("/regenerations", response_model=DataEnvelope[TrainingPlanRegenerationResponse])
def start_regeneration(
    payload: TrainingPlanRegenerationRequest,
    current_user: CurrentUserDependency,
    session: SessionDependency,
) -> DataEnvelope[TrainingPlanRegenerationResponse]:
    ensure_current_user(session, current_user)
    session.scalar(select(UserModel).where(UserModel.id == current_user.id).with_for_update())
    result = _service(session).start(current_user.id, payload, date.today())
    return DataEnvelope(data=_response(result))


def _service(session) -> TrainingPlanRegenerationService:
    athlete_races = SqlAlchemyAthleteRaceRepository(session)
    runs = SqlAlchemyAgentRunRepository(session)
    tasks = SqlAlchemyAgentTaskQueue(session)
    return TrainingPlanRegenerationService(
        profiles=athlete_races,
        race_goals=athlete_races,
        runs=runs,
        tasks=tasks,
        queue_agent_runs=QueueAgentRunHandler(
            runs=runs,
            queue=tasks,
            prompt_version="running-companion-v1",
            provider="local",
            model="deterministic-local-companion",
        ),
    )


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
