from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Any
from uuid import uuid4

from src.application.interfaces.task_queue import AgentTask, AgentTaskQueue, TaskEnvelope
from src.domain.agent_runtime import AgentRun


@dataclass(frozen=True)
class QueuedAgentRun:
    run: AgentRun
    task: AgentTask
    poll_url: str


class QueueAgentRunHandler:
    def __init__(
        self,
        *,
        runs,
        queue: AgentTaskQueue,
        prompt_version: str,
        provider: str | None = None,
        model: str | None = None,
    ) -> None:
        self._runs = runs
        self._queue = queue
        self._prompt_version = prompt_version
        self._provider = provider
        self._model = model

    def queue_run(
        self,
        *,
        user_id: str,
        workflow_name: str,
        trigger_type: str,
        idempotency_key: str,
        payload: dict[str, Any],
        force: bool = False,
    ) -> QueuedAgentRun:
        effective_key = idempotency_key if not force else f"{idempotency_key}:force:{uuid4()}"
        existing_task = self._queue.get_by_idempotency_key(effective_key)
        if existing_task is not None:
            run_id = existing_task.payload.get("run_id")
            existing_run = self._runs.get_run_for_user(user_id, str(run_id) if run_id else None)
            if existing_run is not None and _task_can_be_reused(existing_task.status):
                return QueuedAgentRun(
                    run=existing_run,
                    task=existing_task,
                    poll_url=_poll_url(existing_run.id),
                )
            effective_key = f"{idempotency_key}:retry:{uuid4()}"

        run = self._runs.create_run(
            AgentRun.queue(
                user_id=user_id,
                trigger_type=trigger_type,
                workflow_name=workflow_name,
                prompt_version=self._prompt_version,
                provider=self._provider,
                model=self._model,
                correlation_id=_run_correlation_id(effective_key),
                input_summary=_input_summary(workflow_name, payload),
                metadata={"async": True},
            )
        )
        task = self._queue.enqueue(
            TaskEnvelope(
                task_type="agent.workflow",
                payload={"run_id": run.id, "workflow_name": workflow_name, "input": dict(payload)},
                correlation_id=run.id,
                idempotency_key=effective_key,
            )
        )
        return QueuedAgentRun(run=run, task=task, poll_url=_poll_url(run.id))


def _poll_url(run_id: str | None) -> str:
    return f"/api/v1/agent-runs/{run_id}"


def _task_can_be_reused(status: str) -> bool:
    return status in {"queued", "processing"}


def _run_correlation_id(idempotency_key: str) -> str:
    if len(idempotency_key) <= 120:
        return idempotency_key
    digest = sha256(idempotency_key.encode("utf-8")).hexdigest()[:32]
    return f"{idempotency_key[:83]}:sha:{digest}"


def _input_summary(workflow_name: str, payload: dict[str, Any]) -> str:
    if workflow_name == "daily_recommendation":
        return f"Daily recommendation for {payload.get('anchor_date', 'today')}"
    if workflow_name == "training_plan_generation":
        return "Training plan generation"
    return workflow_name
