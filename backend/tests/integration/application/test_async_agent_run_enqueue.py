from datetime import date, datetime, timezone

from sqlalchemy import select

from src.application.async_agent_runs import QueueAgentRunHandler
from src.infrastructure.database.agent_run_repository import SqlAlchemyAgentRunRepository
from src.infrastructure.database.agent_task_queue import SqlAlchemyAgentTaskQueue
from src.infrastructure.database.models import AgentRunModel, AgentTaskModel, Base, UserModel
from src.infrastructure.database.uow import SqlAlchemyUnitOfWork


def test_queue_agent_run_handler_creates_run_and_task_atomically_with_idempotency(sqlite_session_factory) -> None:
    Base.metadata.create_all(sqlite_session_factory.kw["bind"])

    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        user = UserModel(email="async-run@example.com", display_name="Async Run")
        uow.session.add(user)
        uow.session.flush()
        handler = QueueAgentRunHandler(
            runs=SqlAlchemyAgentRunRepository(uow.session),
            queue=SqlAlchemyAgentTaskQueue(uow.session),
            prompt_version="running-companion-v1",
            provider="local",
            model="deterministic-local-companion",
        )

        first = handler.queue_run(
            user_id=user.id,
            workflow_name="daily_recommendation",
            trigger_type="manual",
            idempotency_key="daily_recommendation:user-1:2027-01-28",
            payload={"anchor_date": date(2027, 1, 28).isoformat()},
        )
        duplicate = handler.queue_run(
            user_id=user.id,
            workflow_name="daily_recommendation",
            trigger_type="manual",
            idempotency_key="daily_recommendation:user-1:2027-01-28",
            payload={"anchor_date": date(2027, 1, 28).isoformat()},
        )
        run_count = len(uow.session.scalars(select(AgentRunModel)).all())
        task_count = len(uow.session.scalars(select(AgentTaskModel)).all())
        task = uow.session.scalar(select(AgentTaskModel))
        uow.commit()

    assert duplicate.run.id == first.run.id
    assert duplicate.task.id == first.task.id
    assert first.run.status == "queued"
    assert first.task.payload["run_id"] == first.run.id
    assert first.task.payload["workflow_name"] == "daily_recommendation"
    assert first.poll_url == f"/api/v1/agent-runs/{first.run.id}"
    assert task.correlation_id == first.run.id
    assert run_count == 1
    assert task_count == 1


def test_queue_agent_run_handler_requeues_after_terminal_task_with_same_idempotency_key(
    sqlite_session_factory,
) -> None:
    Base.metadata.create_all(sqlite_session_factory.kw["bind"])

    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        user = UserModel(email="async-rerun@example.com", display_name="Async Rerun")
        uow.session.add(user)
        uow.session.flush()
        handler = QueueAgentRunHandler(
            runs=SqlAlchemyAgentRunRepository(uow.session),
            queue=SqlAlchemyAgentTaskQueue(uow.session),
            prompt_version="running-companion-v1",
            provider="local",
            model="deterministic-local-companion",
        )
        long_idempotency_key = (
            "training_plan_generation:user-1:race-goal-with-long-identifier-that-pushes-"
            "retry-correlation-beyond-the-agent-run-column-limit::::race"
        )

        first = handler.queue_run(
            user_id=user.id,
            workflow_name="training_plan_generation",
            trigger_type="manual",
            idempotency_key=long_idempotency_key,
            payload={"plan_type": "race"},
        )
        first_task_model = uow.session.get(AgentTaskModel, first.task.id)
        first_run_model = uow.session.get(AgentRunModel, first.run.id)
        first_task_model.status = "failed"
        first_task_model.failed_at = datetime(2027, 1, 28, 8, 0, tzinfo=timezone.utc)
        first_run_model.status = "failed"
        first_run_model.finished_at = datetime(2027, 1, 28, 8, 0, tzinfo=timezone.utc)

        second = handler.queue_run(
            user_id=user.id,
            workflow_name="training_plan_generation",
            trigger_type="manual",
            idempotency_key=long_idempotency_key,
            payload={"plan_type": "race"},
        )
        run_count = len(uow.session.scalars(select(AgentRunModel)).all())
        task_count = len(uow.session.scalars(select(AgentTaskModel)).all())
        uow.commit()

    assert second.run.id != first.run.id
    assert second.task.id != first.task.id
    assert second.task.status == "queued"
    assert second.task.payload["run_id"] == second.run.id
    assert second.task.payload["workflow_name"] == "training_plan_generation"
    assert len(second.run.correlation_id) <= 120
    assert second.task.idempotency_key.startswith(
        "training_plan_generation:user-1:race-goal-with-long-identifier"
    )
    assert run_count == 2
    assert task_count == 2


def test_queue_agent_run_handler_does_not_orphan_run_when_terminal_task_points_to_missing_run(
    sqlite_session_factory,
) -> None:
    Base.metadata.create_all(sqlite_session_factory.kw["bind"])

    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        user = UserModel(email="async-orphan@example.com", display_name="Async Orphan")
        uow.session.add(user)
        uow.session.flush()
        handler = QueueAgentRunHandler(
            runs=SqlAlchemyAgentRunRepository(uow.session),
            queue=SqlAlchemyAgentTaskQueue(uow.session),
            prompt_version="running-companion-v1",
            provider="local",
            model="deterministic-local-companion",
        )

        first = handler.queue_run(
            user_id=user.id,
            workflow_name="training_plan_generation",
            trigger_type="manual",
            idempotency_key="training_plan_generation:user-1:::::race",
            payload={"plan_type": "race"},
        )
        first_task_model = uow.session.get(AgentTaskModel, first.task.id)
        first_run_model = uow.session.get(AgentRunModel, first.run.id)
        first_task_model.status = "failed"
        first_task_model.failed_at = datetime(2027, 1, 28, 8, 0, tzinfo=timezone.utc)
        uow.session.delete(first_run_model)
        uow.session.flush()

        second = handler.queue_run(
            user_id=user.id,
            workflow_name="training_plan_generation",
            trigger_type="manual",
            idempotency_key="training_plan_generation:user-1:::::race",
            payload={"plan_type": "race"},
        )
        uow.commit()

    assert second.run.id != first.run.id
    assert second.task.id != first.task.id
    assert second.task.status == "queued"
    assert second.task.payload["run_id"] == second.run.id
