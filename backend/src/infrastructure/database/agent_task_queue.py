from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.application.interfaces.task_queue import AgentTask, TaskEnvelope

from .models import AgentTaskModel, utc_now


class SqlAlchemyAgentTaskQueue:
    def __init__(self, session: Session) -> None:
        self._session = session

    def enqueue(self, task: TaskEnvelope) -> AgentTask:
        idempotency_key = task.idempotency_key or _default_idempotency_key(task)
        correlation_id = task.correlation_id or idempotency_key
        existing = self._get_model_by_idempotency_key(idempotency_key)
        if existing is not None:
            return _task_from_model(existing)

        now = utc_now()
        model = AgentTaskModel(
            task_type=task.task_type,
            status="queued",
            correlation_id=correlation_id,
            idempotency_key=idempotency_key,
            payload=dict(task.payload),
            available_at=task.available_at or now,
            retry_count=0,
            max_attempts=task.max_attempts,
            created_at=now,
            updated_at=now,
        )
        self._session.add(model)
        try:
            self._session.flush()
        except IntegrityError:
            self._session.rollback()
            existing = self._get_model_by_idempotency_key(idempotency_key)
            if existing is None:
                raise
            return _task_from_model(existing)
        return _task_from_model(model)

    def get_by_idempotency_key(self, idempotency_key: str) -> AgentTask | None:
        model = self._get_model_by_idempotency_key(idempotency_key)
        if model is None:
            return None
        return _task_from_model(model)

    def claim_next(self, *, now: datetime, claim_timeout: timedelta) -> AgentTask | None:
        stale_before = now - claim_timeout
        statement = (
            select(AgentTaskModel)
            .where(
                or_(
                    (AgentTaskModel.status == "queued") & (AgentTaskModel.available_at <= now),
                    (AgentTaskModel.status == "processing") & (AgentTaskModel.claimed_at <= stale_before),
                )
            )
            .order_by(AgentTaskModel.available_at, AgentTaskModel.created_at, AgentTaskModel.id)
            .limit(1)
        )
        model = self._session.scalar(statement)
        if model is None:
            return None
        model.status = "processing"
        model.claimed_at = now
        model.updated_at = now
        self._session.flush()
        return _task_from_model(model)

    def complete(self, task_id: str | None, *, now: datetime) -> AgentTask | None:
        model = self._get(task_id)
        if model is None:
            return None
        model.status = "completed"
        model.completed_at = now
        model.updated_at = now
        self._session.flush()
        return _task_from_model(model)

    def fail(
        self,
        task_id: str | None,
        *,
        error_type: str,
        error_message: str,
        retryable: bool,
        now: datetime,
        retry_delay: timedelta,
    ) -> AgentTask | None:
        model = self._get(task_id)
        if model is None:
            return None

        next_retry_count = model.retry_count + 1
        model.retry_count = next_retry_count
        model.last_error_type = error_type
        model.last_error_message = _summary(error_message)
        model.updated_at = now
        if retryable and next_retry_count < model.max_attempts:
            model.status = "queued"
            model.available_at = now + retry_delay
            model.claimed_at = None
        else:
            model.status = "dead_lettered" if retryable else "failed"
            model.failed_at = now
        self._session.flush()
        return _task_from_model(model)

    def _get(self, task_id: str | None) -> AgentTaskModel | None:
        if task_id is None:
            return None
        return self._session.get(AgentTaskModel, task_id)

    def _get_model_by_idempotency_key(self, idempotency_key: str) -> AgentTaskModel | None:
        return self._session.scalar(
            select(AgentTaskModel).where(AgentTaskModel.idempotency_key == idempotency_key)
        )


def _default_idempotency_key(task: TaskEnvelope) -> str:
    run_id = task.payload.get("run_id")
    if run_id:
        return f"{task.task_type}:{run_id}"
    return f"{task.task_type}:{task.correlation_id or utc_now().isoformat()}"


def _summary(value: str) -> str:
    return value[:2000]


def _task_from_model(model: AgentTaskModel) -> AgentTask:
    return AgentTask(
        id=model.id,
        task_type=model.task_type,
        status=model.status,
        correlation_id=model.correlation_id,
        idempotency_key=model.idempotency_key,
        payload=model.payload or {},
        available_at=model.available_at,
        claimed_at=model.claimed_at,
        completed_at=model.completed_at,
        failed_at=model.failed_at,
        retry_count=model.retry_count,
        max_attempts=model.max_attempts,
        last_error_type=model.last_error_type,
        last_error_message=model.last_error_message,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )
