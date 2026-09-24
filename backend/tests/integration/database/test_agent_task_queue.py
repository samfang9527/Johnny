from datetime import datetime, timedelta, timezone

from src.application.interfaces.task_queue import TaskEnvelope
from src.infrastructure.database.agent_task_queue import SqlAlchemyAgentTaskQueue
from src.infrastructure.database.models import Base
from src.infrastructure.database.uow import SqlAlchemyUnitOfWork


def test_agent_task_queue_enqueues_idempotently_with_aws_like_envelope(sqlite_session_factory) -> None:
    Base.metadata.create_all(sqlite_session_factory.kw["bind"])
    now = datetime(2027, 1, 28, 8, 0, tzinfo=timezone.utc)

    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        queue = SqlAlchemyAgentTaskQueue(uow.session)
        first = queue.enqueue(
            TaskEnvelope(
                task_type="agent.workflow",
                payload={"run_id": "run-1", "workflow_name": "daily_recommendation"},
                correlation_id="correlation-1",
                idempotency_key="daily_recommendation:user-1:2027-01-28",
                available_at=now,
            )
        )
        duplicate = queue.enqueue(
            TaskEnvelope(
                task_type="agent.workflow",
                payload={"run_id": "run-ignored"},
                correlation_id="correlation-ignored",
                idempotency_key="daily_recommendation:user-1:2027-01-28",
                available_at=now + timedelta(minutes=1),
            )
        )
        uow.commit()

    assert duplicate.id == first.id
    assert duplicate.payload == first.payload
    assert first.status == "queued"
    assert first.retry_count == 0
    assert first.max_attempts == 3
    assert first.available_at == now


def test_agent_task_queue_finds_a_task_by_run_correlation_id(sqlite_session_factory) -> None:
    Base.metadata.create_all(sqlite_session_factory.kw["bind"])

    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        queue = SqlAlchemyAgentTaskQueue(uow.session)
        queued = queue.enqueue(
            TaskEnvelope(
                task_type="agent.workflow",
                payload={"run_id": "run-1", "workflow_name": "training_plan_generation"},
                correlation_id="run-1",
                idempotency_key="training_plan_background:user-1:2027-01-29",
            )
        )

        found = queue.get_by_correlation_id("run-1")
        missing = queue.get_by_correlation_id("missing-run")

    assert found is not None
    assert found.id == queued.id
    assert missing is None


def test_agent_task_queue_atomically_requeues_one_terminal_execution_slot(
    sqlite_session_factory,
) -> None:
    Base.metadata.create_all(sqlite_session_factory.kw["bind"])
    now = datetime(2027, 1, 28, 8, 0, tzinfo=timezone.utc)
    execution_key = "training_plan_generation:user-1"

    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        queue = SqlAlchemyAgentTaskQueue(uow.session)
        first = queue.enqueue(
            TaskEnvelope(
                task_type="agent.workflow",
                payload={"run_id": "run-1", "workflow_name": "training_plan_generation"},
                correlation_id="run-1",
                idempotency_key=execution_key,
                available_at=now,
            )
        )
        queue.fail(
            first.id,
            error_type="GenerationFailed",
            error_message="terminal",
            retryable=False,
            now=now,
            retry_delay=timedelta(),
        )

        requeued = queue.enqueue_or_requeue_terminal(
            TaskEnvelope(
                task_type="agent.workflow",
                payload={"run_id": "run-2", "workflow_name": "training_plan_generation"},
                correlation_id="run-2",
                idempotency_key=execution_key,
                available_at=now + timedelta(days=1),
            )
        )
        competing = queue.enqueue_or_requeue_terminal(
            TaskEnvelope(
                task_type="agent.workflow",
                payload={"run_id": "run-3", "workflow_name": "training_plan_generation"},
                correlation_id="run-3",
                idempotency_key=execution_key,
                available_at=now + timedelta(days=1),
            )
        )
        uow.commit()

    assert requeued.id == first.id
    assert competing.id == first.id
    assert competing.status == "queued"
    assert competing.correlation_id == "run-2"
    assert competing.payload["run_id"] == "run-2"
    assert competing.failed_at is None
    assert competing.retry_count == 0


def test_agent_task_queue_claims_oldest_available_then_created_and_reclaims_stale(sqlite_session_factory) -> None:
    Base.metadata.create_all(sqlite_session_factory.kw["bind"])
    now = datetime(2027, 1, 28, 8, 0, tzinfo=timezone.utc)

    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        queue = SqlAlchemyAgentTaskQueue(uow.session)
        later = queue.enqueue(
            TaskEnvelope(
                task_type="agent.workflow",
                payload={"run_id": "later"},
                correlation_id="later",
                idempotency_key="later",
                available_at=now + timedelta(minutes=5),
            )
        )
        first = queue.enqueue(
            TaskEnvelope(
                task_type="agent.workflow",
                payload={"run_id": "first"},
                correlation_id="first",
                idempotency_key="first",
                available_at=now,
            )
        )
        second = queue.enqueue(
            TaskEnvelope(
                task_type="agent.workflow",
                payload={"run_id": "second"},
                correlation_id="second",
                idempotency_key="second",
                available_at=now,
            )
        )

        claimed_first = queue.claim_next(now=now, claim_timeout=timedelta(minutes=5))
        claimed_second = queue.claim_next(now=now, claim_timeout=timedelta(minutes=5))
        none_available = queue.claim_next(now=now, claim_timeout=timedelta(minutes=5))
        reclaimed = queue.claim_next(now=now + timedelta(minutes=6), claim_timeout=timedelta(minutes=5))
        uow.commit()

    assert claimed_first.id == first.id
    assert claimed_first.status == "processing"
    assert claimed_second.id == second.id
    assert none_available is None
    assert reclaimed.id == first.id
    assert later.id not in {claimed_first.id, claimed_second.id, reclaimed.id}


def test_agent_task_queue_completes_retries_fails_and_dead_letters(sqlite_session_factory) -> None:
    Base.metadata.create_all(sqlite_session_factory.kw["bind"])
    now = datetime(2027, 1, 28, 8, 0, tzinfo=timezone.utc)

    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        queue = SqlAlchemyAgentTaskQueue(uow.session)
        completed = queue.enqueue(
            TaskEnvelope(
                task_type="agent.workflow",
                payload={"run_id": "completed"},
                correlation_id="completed",
                idempotency_key="completed",
                available_at=now,
            )
        )
        retrying = queue.enqueue(
            TaskEnvelope(
                task_type="agent.workflow",
                payload={"run_id": "retrying"},
                correlation_id="retrying",
                idempotency_key="retrying",
                available_at=now,
            )
        )
        failed = queue.enqueue(
            TaskEnvelope(
                task_type="agent.workflow",
                payload={"run_id": "failed"},
                correlation_id="failed",
                idempotency_key="failed",
                available_at=now,
            )
        )
        dead = queue.enqueue(
            TaskEnvelope(
                task_type="agent.workflow",
                payload={"run_id": "dead"},
                correlation_id="dead",
                idempotency_key="dead",
                available_at=now,
                max_attempts=1,
            )
        )

        completed = queue.complete(completed.id, now=now)
        retrying = queue.fail(
            retrying.id,
            error_type="TransientGatewayError",
            error_message="temporary outage",
            retryable=True,
            now=now,
            retry_delay=timedelta(seconds=30),
        )
        failed = queue.fail(
            failed.id,
            error_type="MalformedTaskPayload",
            error_message="missing run id",
            retryable=False,
            now=now,
            retry_delay=timedelta(seconds=30),
        )
        dead = queue.fail(
            dead.id,
            error_type="TransientGatewayError",
            error_message="still unavailable",
            retryable=True,
            now=now,
            retry_delay=timedelta(seconds=30),
        )
        uow.commit()

    assert completed.status == "completed"
    assert completed.completed_at == now
    assert retrying.status == "queued"
    assert retrying.retry_count == 1
    assert retrying.available_at == now + timedelta(seconds=30)
    assert failed.status == "failed"
    assert failed.failed_at == now
    assert failed.last_error_message == "missing run id"
    assert dead.status == "dead_lettered"
    assert dead.retry_count == 1
