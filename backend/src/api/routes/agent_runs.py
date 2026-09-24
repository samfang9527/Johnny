from __future__ import annotations

from datetime import date
from uuid import uuid4

from fastapi import APIRouter, Query

from src.api.dependencies import CurrentUserDependency, SessionDependency, ensure_current_user
from src.api.errors import ApiNotFoundError
from src.api.schemas.agent_runs import (
    AgentRunResponse,
    AgentRunStepResponse,
    DailyRecommendationRunRequest,
    QueuedAgentRunResponse,
    TrainingPlanGenerationRunRequest,
)
from src.api.schemas.common import DEFAULT_PAGE_LIMIT, DataEnvelope, ListEnvelope, PageLimit, PageOffset, list_envelope, page_query_limit
from src.application.async_agent_runs import QueueAgentRunHandler
from src.domain.agent_runtime import AgentRun, AgentRunStep
from src.infrastructure.database.agent_run_repository import SqlAlchemyAgentRunRepository
from src.infrastructure.database.agent_task_queue import SqlAlchemyAgentTaskQueue


router = APIRouter(prefix="/agent-runs", tags=["agent-runs"])


@router.post("/daily-recommendation", response_model=DataEnvelope[QueuedAgentRunResponse])
def queue_daily_recommendation(
    payload: DailyRecommendationRunRequest,
    current_user: CurrentUserDependency,
    session: SessionDependency,
) -> DataEnvelope[QueuedAgentRunResponse]:
    ensure_current_user(session, current_user)
    anchor_date = payload.anchor_date or date.today()
    idempotency_key = f"daily_recommendation:{current_user.id}:{anchor_date.isoformat()}"
    if payload.force:
        idempotency_key = f"{idempotency_key}:force:{uuid4()}"
    result = _queue_handler(session).queue_run(
        user_id=current_user.id,
        workflow_name="daily_recommendation",
        trigger_type="manual",
        idempotency_key=idempotency_key,
        payload={"anchor_date": anchor_date.isoformat(), "force": payload.force},
    )
    return DataEnvelope(data=_queued_response(result))


@router.post("/training-plan-generation", response_model=DataEnvelope[QueuedAgentRunResponse])
def queue_training_plan_generation(
    payload: TrainingPlanGenerationRunRequest,
    current_user: CurrentUserDependency,
    session: SessionDependency,
) -> DataEnvelope[QueuedAgentRunResponse]:
    ensure_current_user(session, current_user)
    idempotency_key = f"training_plan_generation:{current_user.id}"
    result = _queue_handler(session).queue_run(
        user_id=current_user.id,
        workflow_name="training_plan_generation",
        trigger_type="manual",
        idempotency_key=idempotency_key,
        payload=payload.model_dump(mode="json"),
        requeue_terminal=True,
    )
    return DataEnvelope(data=_queued_response(result))


@router.get("", response_model=ListEnvelope[AgentRunResponse])
def list_agent_runs(
    current_user: CurrentUserDependency,
    session: SessionDependency,
    workflow_name: str | None = Query(default=None),
    status: str | None = Query(default=None),
    limit: PageLimit = DEFAULT_PAGE_LIMIT,
    offset: PageOffset = 0,
) -> ListEnvelope[AgentRunResponse]:
    runs = SqlAlchemyAgentRunRepository(session).list_runs_for_user(
        current_user.id,
        workflow_name=workflow_name,
        status=status,
        limit=page_query_limit(limit),
        offset=offset,
    )
    return list_envelope([_run_response(run) for run in runs], limit=limit, offset=offset)


@router.get("/{run_id}", response_model=DataEnvelope[AgentRunResponse])
def get_agent_run(
    run_id: str,
    current_user: CurrentUserDependency,
    session: SessionDependency,
) -> DataEnvelope[AgentRunResponse]:
    run = SqlAlchemyAgentRunRepository(session).get_run_for_user(current_user.id, run_id)
    if run is None:
        raise ApiNotFoundError("agent run not found")
    return DataEnvelope(data=_run_response(run))


@router.get("/{run_id}/steps", response_model=ListEnvelope[AgentRunStepResponse])
def list_agent_run_steps(
    run_id: str,
    current_user: CurrentUserDependency,
    session: SessionDependency,
    limit: PageLimit = DEFAULT_PAGE_LIMIT,
    offset: PageOffset = 0,
) -> ListEnvelope[AgentRunStepResponse]:
    steps = SqlAlchemyAgentRunRepository(session).list_steps_for_user_run(current_user.id, run_id)
    return list_envelope([_step_response(step) for step in steps[offset : offset + page_query_limit(limit)]], limit=limit, offset=offset)


def _queue_handler(session) -> QueueAgentRunHandler:
    return QueueAgentRunHandler(
        runs=SqlAlchemyAgentRunRepository(session),
        queue=SqlAlchemyAgentTaskQueue(session),
        prompt_version="running-companion-v1",
        provider="local",
        model="deterministic-local-companion",
    )


def _queued_response(result) -> QueuedAgentRunResponse:
    return QueuedAgentRunResponse(
        run_id=result.run.id,
        status=result.run.status,
        workflow_name=result.run.workflow_name,
        poll_url=result.poll_url,
    )


def _run_response(run: AgentRun) -> AgentRunResponse:
    return AgentRunResponse(
        id=run.id,
        user_id=run.user_id,
        status=run.status,
        trigger_type=run.trigger_type,
        workflow_name=run.workflow_name,
        prompt_version=run.prompt_version,
        provider=run.provider,
        model=run.model,
        correlation_id=run.correlation_id,
        started_at=run.started_at,
        finished_at=run.finished_at,
        latency_ms=run.latency_ms,
        input_tokens=run.input_tokens,
        output_tokens=run.output_tokens,
        total_tokens=run.total_tokens,
        input_summary=run.input_summary,
        output_summary=run.output_summary,
        error_type=run.error_type,
        error_message=run.error_message,
        recommendation_id=run.recommendation_id,
    )


def _step_response(step: AgentRunStep) -> AgentRunStepResponse:
    return AgentRunStepResponse(
        id=step.id,
        agent_run_id=step.agent_run_id,
        sequence_number=step.sequence_number,
        step_type=step.step_type,
        name=step.name,
        status=step.status,
        tool_name=step.tool_name,
        started_at=step.started_at,
        finished_at=step.finished_at,
        latency_ms=step.latency_ms,
        input_summary=step.input_summary,
        output_summary=step.output_summary,
        error_type=step.error_type,
        error_message=step.error_message,
        payload=step.payload or {},
    )
