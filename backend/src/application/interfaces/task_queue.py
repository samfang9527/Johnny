from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol


@dataclass(frozen=True)
class TaskEnvelope:
    task_type: str
    payload: dict
    correlation_id: str | None = None
    idempotency_key: str | None = None
    available_at: datetime | None = None
    max_attempts: int = 3


@dataclass(frozen=True)
class AgentTask:
    id: str
    task_type: str
    status: str
    correlation_id: str
    idempotency_key: str
    payload: dict
    available_at: datetime
    claimed_at: datetime | None
    completed_at: datetime | None
    failed_at: datetime | None
    retry_count: int
    max_attempts: int
    last_error_type: str | None
    last_error_message: str | None
    created_at: datetime
    updated_at: datetime


class TaskQueue(Protocol):
    def publish(self, task: TaskEnvelope) -> None:
        ...


class AgentTaskQueue(Protocol):
    def get_by_idempotency_key(self, idempotency_key: str) -> AgentTask | None:
        ...

    def enqueue(self, task: TaskEnvelope) -> AgentTask:
        ...

    def claim_next(self, *, now: datetime, claim_timeout: timedelta) -> AgentTask | None:
        ...

    def complete(self, task_id: str | None, *, now: datetime) -> AgentTask | None:
        ...

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
        ...
