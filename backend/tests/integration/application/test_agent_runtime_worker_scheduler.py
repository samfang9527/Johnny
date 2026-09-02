from datetime import date
from pathlib import Path
import sys

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.agent_runtime import main, schedule_once, work_drain
from src.api.dependencies import get_session
from src.application.interfaces.task_queue import TaskEnvelope
from src.api.dependencies import CurrentUser, ensure_current_user
from src.infrastructure.database.agent_run_repository import SqlAlchemyAgentRunRepository
from src.infrastructure.database.agent_task_queue import SqlAlchemyAgentTaskQueue
from src.infrastructure.database.models import AgentTaskModel, Base, RecommendationModel, TrainingPlanModel
from src.infrastructure.database.uow import SqlAlchemyUnitOfWork
from src.main import create_app


def _create_context_ready_user(session, user_id: str) -> None:
    ensure_current_user(session, CurrentUser(id=user_id))
    session.execute(
        TrainingPlanModel.__table__.insert().values(
            id=f"plan-{user_id}",
            user_id=user_id,
            name="Active Plan",
            status="active",
            starts_on=date(2027, 1, 1),
            ends_on=date(2027, 2, 28),
        )
    )
    session.execute(
        Base.metadata.tables["athlete_profiles"].insert().values(
            id=f"profile-{user_id}",
            user_id=user_id,
            timezone="UTC",
            experience_level="intermediate",
            metadata_json={},
        )
    )


def test_schedule_once_enqueues_today_daily_jobs_for_context_ready_active_users(sqlite_session_factory) -> None:
    Base.metadata.create_all(sqlite_session_factory.kw["bind"])
    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        _create_context_ready_user(uow.session, "eligible-user")
        ensure_current_user(uow.session, CurrentUser(id="missing-profile"))
        uow.session.execute(
            TrainingPlanModel.__table__.insert().values(
                id="plan-missing-profile",
                user_id="missing-profile",
                name="Active Plan",
                status="active",
                starts_on=date(2027, 1, 1),
                ends_on=date(2027, 2, 28),
            )
        )

        queued = schedule_once(uow.session, anchor_date=date(2027, 1, 28))
        duplicate = schedule_once(uow.session, anchor_date=date(2027, 1, 28))
        tasks = uow.session.scalars(select(AgentTaskModel)).all()
        uow.commit()

    assert queued == 1
    assert duplicate == 0
    assert len(tasks) == 1
    assert tasks[0].payload["input"]["anchor_date"] == "2027-01-28"


def test_work_drain_processes_daily_and_training_plan_generation_tasks(sqlite_session_factory) -> None:
    Base.metadata.create_all(sqlite_session_factory.kw["bind"])
    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        _create_context_ready_user(uow.session, "worker-user")
        handler_runs = SqlAlchemyAgentRunRepository(uow.session)
        queue = SqlAlchemyAgentTaskQueue(uow.session)
        from src.application.async_agent_runs import QueueAgentRunHandler

        handler = QueueAgentRunHandler(
            runs=handler_runs,
            queue=queue,
            prompt_version="running-companion-v1",
            provider="local",
            model="deterministic-local-companion",
        )
        daily = handler.queue_run(
            user_id="worker-user",
            workflow_name="daily_recommendation",
            trigger_type="manual",
            idempotency_key="daily:worker-user:2027-01-28",
            payload={"anchor_date": "2027-01-28"},
        )
        training = handler.queue_run(
            user_id="worker-user",
            workflow_name="training_plan_generation",
            trigger_type="manual",
            idempotency_key="training:worker-user:2027-01-28",
            payload={"plan_type": "base", "starts_on": "2027-01-01"},
        )

        processed = work_drain(uow.session)
        daily_run = handler_runs.get_run_for_user("worker-user", daily.run.id)
        training_run = handler_runs.get_run_for_user("worker-user", training.run.id)
        draft_count = len(uow.session.scalars(select(TrainingPlanModel).where(TrainingPlanModel.status == "draft")).all())
        recommendation_count = len(uow.session.scalars(select(RecommendationModel)).all())
        uow.commit()

    assert processed == 2
    assert daily_run.status == "completed"
    assert training_run.status == "completed"
    assert draft_count == 1
    assert recommendation_count == 2


def test_work_drain_marks_unknown_and_malformed_tasks_non_retryable(sqlite_session_factory) -> None:
    Base.metadata.create_all(sqlite_session_factory.kw["bind"])
    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        queue = SqlAlchemyAgentTaskQueue(uow.session)
        queue.enqueue(
            task=TaskEnvelope(
                task_type="unknown",
                payload={},
                correlation_id="unknown",
                idempotency_key="unknown",
            )
        )
        queue.enqueue(
            task=TaskEnvelope(
                task_type="agent.workflow",
                payload={"workflow_name": "daily_recommendation"},
                correlation_id="malformed",
                idempotency_key="malformed",
            )
        )

        processed = work_drain(uow.session)
        statuses = [
            task.status for task in uow.session.scalars(select(AgentTaskModel).order_by(AgentTaskModel.created_at))
        ]
        errors = [
            task.last_error_type
            for task in uow.session.scalars(select(AgentTaskModel).order_by(AgentTaskModel.created_at))
        ]
        uow.commit()

    assert processed == 2
    assert statuses == ["failed", "failed"]
    assert errors == ["UnknownTaskType", "MalformedTaskPayload"]


def test_agent_runtime_cli_work_drain_does_not_require_smoke_openai_flag(tmp_path, monkeypatch, capsys) -> None:
    database_url = f"sqlite:///{tmp_path / 'agent-runtime-cli.db'}"
    monkeypatch.setattr(
        sys,
        "argv",
        ["agent_runtime.py", "--database-url", database_url, "work-drain"],
    )

    result = main()

    assert result == 0
    assert "processed=0" in capsys.readouterr().out


def test_smoke_flow_queues_with_http_drains_worker_and_polls_completion(monkeypatch) -> None:
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(dbapi_connection, connection_record) -> None:  # noqa: ANN001
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)

    def override_session():
        session = session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    app = create_app()
    app.dependency_overrides[get_session] = override_session
    client = TestClient(app)
    headers = {"X-Johnny-User-Id": "smoke-user"}

    daily = client.post(
        "/api/v1/agent-runs/daily-recommendation",
        headers=headers,
        json={"anchor_date": "2027-01-28"},
    ).json()["data"]
    training = client.post(
        "/api/v1/agent-runs/training-plan-generation",
        headers=headers,
        json={"plan_type": "base", "starts_on": "2027-01-01"},
    ).json()["data"]

    with session_factory() as session:
        processed = work_drain(session)
        session.commit()

    daily_run = client.get(daily["poll_url"], headers=headers).json()["data"]
    training_run = client.get(training["poll_url"], headers=headers).json()["data"]
    recommendations = client.get("/api/v1/recommendations", headers=headers).json()["data"]
    plans = client.get("/api/v1/training-plans", headers=headers).json()["data"]

    assert processed == 2
    assert daily_run["status"] == "completed"
    assert training_run["status"] == "completed"
    assert len(recommendations) == 2
    assert any(plan["status"] == "draft" for plan in plans)
