from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.domain.agent_runtime import AgentContextSource, AgentRun, AgentRunStep

from .models import AgentContextSourceModel, AgentRunModel, AgentRunStepModel


class SqlAlchemyAgentRunRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create_run(self, run: AgentRun) -> AgentRun:
        model = AgentRunModel(
            user_id=run.user_id,
            recommendation_id=run.recommendation_id,
            status=run.status,
            provider=run.provider,
            model=run.model,
            trigger_type=run.trigger_type,
            workflow_name=run.workflow_name,
            prompt_version=run.prompt_version,
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
            trace_ref=run.trace_ref,
            trace=run.trace or {},
            metadata_json=run.metadata or {},
        )
        self._session.add(model)
        self._session.flush()
        return _run_from_model(model)

    def get_run_for_user(self, user_id: str, run_id: str | None) -> AgentRun | None:
        if run_id is None:
            return None
        model = self._session.scalar(
            select(AgentRunModel).where(
                AgentRunModel.id == run_id,
                AgentRunModel.user_id == user_id,
            )
        )
        if model is None:
            return None
        return _run_from_model(model)

    def list_runs_for_user(
        self,
        user_id: str,
        *,
        workflow_name: str | None = None,
        status: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[AgentRun]:
        statement = select(AgentRunModel).where(AgentRunModel.user_id == user_id)
        if workflow_name is not None:
            statement = statement.where(AgentRunModel.workflow_name == workflow_name)
        if status is not None:
            statement = statement.where(AgentRunModel.status == status)
        statement = statement.order_by(AgentRunModel.created_at.desc(), AgentRunModel.id.desc()).offset(offset)
        if limit is not None:
            statement = statement.limit(limit)
        return [_run_from_model(model) for model in self._session.scalars(statement)]

    def record_step(self, step: AgentRunStep) -> AgentRunStep:
        model = AgentRunStepModel(
            agent_run_id=step.agent_run_id,
            sequence_number=step.sequence_number,
            step_type=step.step_type,
            name=step.name,
            status=step.status,
            started_at=step.started_at,
            finished_at=step.finished_at,
            latency_ms=step.latency_ms,
            input_tokens=step.input_tokens,
            output_tokens=step.output_tokens,
            tool_name=step.tool_name,
            error_type=step.error_type,
            error_message=step.error_message,
            input_summary=step.input_summary,
            output_summary=step.output_summary,
            payload=step.payload or {},
        )
        self._session.add(model)
        self._session.flush()
        return _step_from_model(model)

    def list_steps_for_run(self, agent_run_id: str) -> list[AgentRunStep]:
        statement = (
            select(AgentRunStepModel)
            .where(AgentRunStepModel.agent_run_id == agent_run_id)
            .order_by(AgentRunStepModel.sequence_number, AgentRunStepModel.id)
        )
        return [_step_from_model(model) for model in self._session.scalars(statement)]

    def list_steps_for_user_run(self, user_id: str, agent_run_id: str | None) -> list[AgentRunStep]:
        if agent_run_id is None:
            return []
        run = self._session.scalar(
            select(AgentRunModel.id).where(
                AgentRunModel.id == agent_run_id,
                AgentRunModel.user_id == user_id,
            )
        )
        if run is None:
            return []
        return self.list_steps_for_run(agent_run_id)

    def record_context_source(self, source: AgentContextSource) -> AgentContextSource:
        model = AgentContextSourceModel(
            agent_run_id=source.agent_run_id,
            source_type=source.source_type,
            source_id=source.source_id,
            source_summary=source.source_summary,
            relevance_score=source.relevance_score,
            metadata_json=source.metadata or {},
        )
        self._session.add(model)
        self._session.flush()
        return _context_source_from_model(model)

    def list_context_sources_for_run(self, agent_run_id: str) -> list[AgentContextSource]:
        statement = (
            select(AgentContextSourceModel)
            .where(AgentContextSourceModel.agent_run_id == agent_run_id)
            .order_by(AgentContextSourceModel.created_at, AgentContextSourceModel.id)
        )
        return [_context_source_from_model(model) for model in self._session.scalars(statement)]

    def complete_run(self, run: AgentRun) -> AgentRun:
        model = self._get_run_model(run)
        _update_model_from_run(model, run)
        self._session.flush()
        return _run_from_model(model)

    def fail_run(self, run: AgentRun) -> AgentRun:
        model = self._get_run_model(run)
        _update_model_from_run(model, run)
        self._session.flush()
        return _run_from_model(model)

    def _get_run_model(self, run: AgentRun) -> AgentRunModel:
        if run.id is None:
            raise ValueError("agent run id is required")
        model = self._session.scalar(
            select(AgentRunModel).where(
                AgentRunModel.id == run.id,
                AgentRunModel.user_id == run.user_id,
            )
        )
        if model is None:
            raise ValueError(f"Agent run not found: {run.id}")
        return model


def _update_model_from_run(model: AgentRunModel, run: AgentRun) -> None:
    model.recommendation_id = run.recommendation_id
    model.status = run.status
    model.provider = run.provider
    model.model = run.model
    model.trigger_type = run.trigger_type
    model.workflow_name = run.workflow_name
    model.prompt_version = run.prompt_version
    model.correlation_id = run.correlation_id
    model.started_at = run.started_at
    model.finished_at = run.finished_at
    model.latency_ms = run.latency_ms
    model.input_tokens = run.input_tokens
    model.output_tokens = run.output_tokens
    model.total_tokens = run.total_tokens
    model.input_summary = run.input_summary
    model.output_summary = run.output_summary
    model.error_type = run.error_type
    model.error_message = run.error_message
    model.trace_ref = run.trace_ref
    model.trace = run.trace or {}
    model.metadata_json = run.metadata or {}


def _run_from_model(model: AgentRunModel) -> AgentRun:
    return AgentRun(
        id=model.id,
        user_id=model.user_id,
        recommendation_id=model.recommendation_id,
        status=model.status,
        provider=model.provider,
        model=model.model,
        trigger_type=model.trigger_type or "unknown",
        workflow_name=model.workflow_name or "unknown",
        prompt_version=model.prompt_version or "unknown",
        correlation_id=model.correlation_id,
        started_at=model.started_at,
        finished_at=model.finished_at,
        latency_ms=model.latency_ms,
        input_tokens=model.input_tokens,
        output_tokens=model.output_tokens,
        total_tokens=model.total_tokens,
        input_summary=model.input_summary,
        output_summary=model.output_summary,
        error_type=model.error_type,
        error_message=model.error_message,
        trace_ref=model.trace_ref,
        trace=model.trace or {},
        metadata=model.metadata_json or {},
    )


def _step_from_model(model: AgentRunStepModel) -> AgentRunStep:
    return AgentRunStep(
        id=model.id,
        agent_run_id=model.agent_run_id,
        sequence_number=model.sequence_number,
        step_type=model.step_type,
        name=model.name,
        status=model.status,
        started_at=model.started_at,
        finished_at=model.finished_at,
        latency_ms=model.latency_ms,
        input_tokens=model.input_tokens,
        output_tokens=model.output_tokens,
        tool_name=model.tool_name,
        error_type=model.error_type,
        error_message=model.error_message,
        input_summary=model.input_summary,
        output_summary=model.output_summary,
        payload=model.payload or {},
    )


def _context_source_from_model(model: AgentContextSourceModel) -> AgentContextSource:
    return AgentContextSource.create(
        id=model.id,
        agent_run_id=model.agent_run_id,
        source_type=model.source_type,
        source_id=model.source_id,
        source_summary=model.source_summary,
        relevance_score=model.relevance_score,
        metadata=model.metadata_json or {},
    )
