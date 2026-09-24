from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import sys

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import scripts.agent_runtime as agent_runtime
from scripts.agent_runtime import main, schedule_once, work_drain
from src.application.async_agent_runs import QueueAgentRunHandler
from src.application.training_plan_regeneration import BackgroundProjectionCandidate, RegenerationStrategy
from src.api.dependencies import get_session
from src.application.interfaces.task_queue import TaskEnvelope
from src.api.dependencies import CurrentUser, ensure_current_user
from src.infrastructure.database.agent_run_repository import SqlAlchemyAgentRunRepository
from src.infrastructure.database.agent_task_queue import SqlAlchemyAgentTaskQueue
from src.infrastructure.database.models import (
    AgentRunModel,
    AgentTaskModel,
    Base,
    RaceModel,
    RecommendationModel,
    TrainingPlanModel,
    UserModel,
)
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
        _create_context_ready_user(uow.session, "another-eligible-user")
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

    assert queued == 3
    assert duplicate == 0
    assert len(tasks) == 3
    daily_tasks = [task for task in tasks if task.task_type == "agent.workflow"]
    daily_check_tasks = [task for task in tasks if task.task_type == "training-plan.daily-check"]
    assert len(daily_tasks) == 2
    assert {task.payload["input"]["anchor_date"] for task in daily_tasks} == {"2027-01-28"}
    assert len(daily_check_tasks) == 1
    assert daily_check_tasks[0].payload == {"anchor_date": "2027-01-28"}


def test_work_drain_daily_check_queues_one_background_generation_for_repeated_checks(sqlite_session_factory) -> None:
    Base.metadata.create_all(sqlite_session_factory.kw["bind"])
    anchor = datetime.now(timezone.utc).date()
    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        _create_context_ready_user(uow.session, "background-user")
        uow.session.execute(
            TrainingPlanModel.__table__.update()
            .where(TrainingPlanModel.id == "plan-background-user")
            .values(
                starts_on=anchor - timedelta(days=34),
                ends_on=anchor - timedelta(days=7),
            )
        )
        queue = SqlAlchemyAgentTaskQueue(uow.session)
        for suffix in ("first", "repeat"):
            queue.enqueue(
                TaskEnvelope(
                    task_type="training-plan.daily-check",
                    payload={"anchor_date": anchor.isoformat()},
                    correlation_id=f"daily-check:{suffix}",
                    idempotency_key=f"daily-check:{anchor.isoformat()}:{suffix}",
                )
            )

        processed = work_drain(uow.session)
        generation_runs = list(
            uow.session.scalars(
                select(AgentRunModel).where(AgentRunModel.workflow_name == "training_plan_generation")
            )
        )
        generation_tasks = list(
            uow.session.scalars(
                select(AgentTaskModel).where(
                    AgentTaskModel.task_type == "agent.workflow",
                    AgentTaskModel.payload["workflow_name"].as_string() == "training_plan_generation",
                )
            )
        )
        uow.commit()

    assert processed == 3
    assert len(generation_runs) == 1
    assert len(generation_tasks) == 1
    assert generation_runs[0].metadata_json["manual_regeneration"] is False
    assert generation_runs[0].metadata_json["trigger_type"] == "scheduled"


def test_work_drain_daily_check_continues_after_candidate_queue_failure(sqlite_session_factory, monkeypatch, caplog) -> None:
    Base.metadata.create_all(sqlite_session_factory.kw["bind"])
    strategy = RegenerationStrategy(
        race_id=None,
        plan_type="maintenance",
        reason="no_future_race",
        starts_on=date(2027, 2, 1),
        plan_horizon_weeks=4,
    )
    failed_candidate = BackgroundProjectionCandidate(
        user_id="failed-user",
        previous_plan_id="failed-plan",
        previous_ends_on=date(2027, 1, 24),
        strategy=strategy,
    )
    succeeding_candidate = BackgroundProjectionCandidate(
        user_id="succeeding-user",
        previous_plan_id="succeeding-plan",
        previous_ends_on=date(2027, 1, 24),
        strategy=strategy,
    )

    class BackgroundService:
        def find_users_needing_projection(self, today):
            assert today == date(2027, 1, 31)
            return [failed_candidate, succeeding_candidate]

        def queue_background_generation(self, candidate):
            if candidate.user_id == "failed-user":
                raise ConnectionError("background queue unavailable")
            queued_user_ids.append(candidate.user_id)

    queued_user_ids: list[str] = []
    monkeypatch.setattr(agent_runtime, "_training_plan_regeneration_service", lambda session: BackgroundService())

    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        queue = SqlAlchemyAgentTaskQueue(uow.session)
        task = queue.enqueue(
            TaskEnvelope(
                task_type="training-plan.daily-check",
                payload={"anchor_date": "2027-01-31"},
                correlation_id="daily-check-candidate-failure",
                idempotency_key="daily-check-candidate-failure",
            )
        )

        processed = work_drain(uow.session)
        persisted_task = uow.session.get(AgentTaskModel, task.id)
        uow.commit()

    assert processed == 1
    assert queued_user_ids == ["succeeding-user"]
    assert persisted_task.status == "completed"
    assert "training plan background generation queue failed" in caplog.text


def test_work_drain_daily_check_retries_discovery_failure(sqlite_session_factory, monkeypatch, caplog) -> None:
    Base.metadata.create_all(sqlite_session_factory.kw["bind"])

    class UnavailableBackgroundService:
        def find_users_needing_projection(self, today):
            raise ConnectionError("database unavailable")

    monkeypatch.setattr(
        agent_runtime,
        "_training_plan_regeneration_service",
        lambda session: UnavailableBackgroundService(),
    )

    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        queue = SqlAlchemyAgentTaskQueue(uow.session)
        task = queue.enqueue(
            TaskEnvelope(
                task_type="training-plan.daily-check",
                payload={"anchor_date": "2027-01-31"},
                correlation_id="daily-check-discovery-failure",
                idempotency_key="daily-check-discovery-failure",
            )
        )

        processed = work_drain(uow.session)
        persisted_task = uow.session.get(AgentTaskModel, task.id)
        uow.commit()

    assert processed == 1
    assert persisted_task.status == "queued"
    assert persisted_task.retry_count == 1
    assert persisted_task.last_error_type == "ConnectionError"
    assert "training plan daily check discovery failed" in caplog.text


def test_work_drain_daily_check_isolates_database_discovery_failure(
    sqlite_session_factory,
    monkeypatch,
) -> None:
    Base.metadata.create_all(sqlite_session_factory.kw["bind"])

    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        ensure_current_user(uow.session, CurrentUser(id="discovery-owner"))
        uow.commit()

    class DatabaseFailingBackgroundService:
        def __init__(self, session) -> None:
            self._session = session

        def find_users_needing_projection(self, today):
            self._session.add(
                UserModel(
                    id="duplicate-discovery-email",
                    email="discovery-owner@local.johnny",
                    display_name="Duplicate",
                )
            )
            self._session.flush()

    monkeypatch.setattr(
        agent_runtime,
        "_training_plan_regeneration_service",
        lambda session: DatabaseFailingBackgroundService(session),
    )

    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        task = SqlAlchemyAgentTaskQueue(uow.session).enqueue(
            TaskEnvelope(
                task_type="training-plan.daily-check",
                payload={"anchor_date": "2027-01-31"},
                correlation_id="daily-check-database-discovery-failure",
                idempotency_key="daily-check-database-discovery-failure",
            )
        )

        processed = work_drain(uow.session)
        persisted_task = uow.session.get(AgentTaskModel, task.id)
        uow.commit()

    assert processed == 1
    assert persisted_task.status == "queued"
    assert persisted_task.retry_count == 1
    assert persisted_task.last_error_type == "IntegrityError"


def test_work_drain_daily_check_isolates_database_queue_failure_per_candidate(
    sqlite_session_factory,
    monkeypatch,
) -> None:
    Base.metadata.create_all(sqlite_session_factory.kw["bind"])
    strategy = RegenerationStrategy(
        race_id=None,
        plan_type="maintenance",
        reason="no_future_race",
        starts_on=date(2027, 2, 1),
        plan_horizon_weeks=4,
    )
    candidates = [
        BackgroundProjectionCandidate(
            user_id="database-failure-user",
            previous_plan_id="database-failure-plan",
            previous_ends_on=date(2027, 1, 24),
            strategy=strategy,
        ),
        BackgroundProjectionCandidate(
            user_id="database-success-user",
            previous_plan_id="database-success-plan",
            previous_ends_on=date(2027, 1, 24),
            strategy=strategy,
        ),
    ]

    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        ensure_current_user(uow.session, CurrentUser(id="queue-owner"))
        uow.commit()

    queued_user_ids: list[str] = []

    class DatabaseFailingBackgroundService:
        def __init__(self, session) -> None:
            self._session = session

        def find_users_needing_projection(self, today):
            return candidates

        def queue_background_generation(self, candidate):
            if candidate.user_id == "database-failure-user":
                self._session.add(
                    UserModel(
                        id="duplicate-queue-email",
                        email="queue-owner@local.johnny",
                        display_name="Duplicate",
                    )
                )
                self._session.flush()
            self._session.scalar(select(UserModel.id).where(UserModel.id == "queue-owner"))
            queued_user_ids.append(candidate.user_id)

    monkeypatch.setattr(
        agent_runtime,
        "_training_plan_regeneration_service",
        lambda session: DatabaseFailingBackgroundService(session),
    )

    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        task = SqlAlchemyAgentTaskQueue(uow.session).enqueue(
            TaskEnvelope(
                task_type="training-plan.daily-check",
                payload={"anchor_date": "2027-01-31"},
                correlation_id="daily-check-database-candidate-failure",
                idempotency_key="daily-check-database-candidate-failure",
            )
        )

        processed = work_drain(uow.session)
        persisted_task = uow.session.get(AgentTaskModel, task.id)
        uow.commit()

    assert processed == 1
    assert queued_user_ids == ["database-success-user"]
    assert persisted_task.status == "completed"


def test_scheduled_training_plan_refreshes_stale_dates_and_race_before_execution(
    sqlite_session_factory,
    monkeypatch,
) -> None:
    Base.metadata.create_all(sqlite_session_factory.kw["bind"])
    execution_instant = datetime(2027, 1, 10, 12, tzinfo=timezone.utc)
    previous_ends_on = date(2027, 1, 1)
    stale_starts_on = date(2027, 1, 9)
    refreshed_starts_on = date(2027, 1, 11)
    monkeypatch.setattr(agent_runtime, "_utc_now", lambda: execution_instant)

    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        _create_context_ready_user(uow.session, "refresh-user")
        uow.session.execute(
            TrainingPlanModel.__table__.update()
            .where(TrainingPlanModel.id == "plan-refresh-user")
            .values(
                starts_on=previous_ends_on - timedelta(days=27),
                ends_on=previous_ends_on,
            )
        )
        uow.session.execute(
            RaceModel.__table__.insert(),
            [
                {
                    "id": "cancelled-primary",
                    "user_id": "refresh-user",
                    "name": "Cancelled Primary",
                    "race_date": date(2027, 2, 1),
                    "distance_meters": 21097,
                    "status": "cancelled",
                    "metadata_json": {"priority": "primary"},
                },
                {
                    "id": "active-secondary",
                    "user_id": "refresh-user",
                    "name": "Active Secondary",
                    "race_date": date(2027, 2, 15),
                    "distance_meters": 21097,
                    "status": "active",
                    "metadata_json": {"priority": "secondary"},
                },
                {
                    "id": "planned-primary",
                    "user_id": "refresh-user",
                    "name": "Planned Primary",
                    "race_date": date(2027, 3, 1),
                    "distance_meters": 21097,
                    "status": "planned",
                    "metadata_json": {"priority": "primary"},
                },
            ],
        )
        queued = QueueAgentRunHandler(
            runs=SqlAlchemyAgentRunRepository(uow.session),
            queue=SqlAlchemyAgentTaskQueue(uow.session),
            prompt_version="running-companion-v1",
            provider="local",
            model="deterministic-local-companion",
        ).queue_run(
            user_id="refresh-user",
            workflow_name="training_plan_generation",
            trigger_type="scheduled",
            idempotency_key="training_plan_generation:refresh-user",
            payload={
                "race_id": "cancelled-primary",
                "plan_type": "race",
                "starts_on": stale_starts_on.isoformat(),
                "plan_horizon_weeks": 4,
                "manual_regeneration": False,
                "trigger_type": "scheduled",
                "replace_active_projection": True,
                "previous_ends_on": previous_ends_on.isoformat(),
            },
            requeue_terminal=True,
        )

        processed = work_drain(uow.session)
        refreshed_run = uow.session.get(AgentRunModel, queued.run.id)
        refreshed_task = uow.session.get(AgentTaskModel, queued.task.id)
        generated_plan = uow.session.scalar(
            select(TrainingPlanModel).where(
                TrainingPlanModel.user_id == "refresh-user",
                TrainingPlanModel.status == "active",
            )
        )
        previous_plan = uow.session.get(TrainingPlanModel, "plan-refresh-user")
        uow.commit()

    assert processed == 1
    assert refreshed_run.status == "completed"
    assert refreshed_run.metadata_json["race_id"] == "planned-primary"
    assert refreshed_run.metadata_json["starts_on"] == refreshed_starts_on.isoformat()
    assert refreshed_run.metadata_json["plan_type"] == "race"
    assert refreshed_run.metadata_json["replace_active_projection"] is True
    assert refreshed_task.payload["input"]["race_id"] == "planned-primary"
    assert refreshed_task.payload["input"]["starts_on"] == refreshed_starts_on.isoformat()
    assert generated_plan is not None
    assert generated_plan.race_id == "planned-primary"
    assert generated_plan.starts_on == refreshed_starts_on
    assert previous_plan.status == "superseded"


def test_legacy_scheduled_training_plan_derives_previous_end_before_execution(
    sqlite_session_factory,
    monkeypatch,
) -> None:
    Base.metadata.create_all(sqlite_session_factory.kw["bind"])
    execution_instant = datetime(2027, 1, 10, 12, tzinfo=timezone.utc)
    previous_ends_on = date(2027, 1, 1)
    refreshed_starts_on = date(2027, 1, 11)
    monkeypatch.setattr(agent_runtime, "_utc_now", lambda: execution_instant)

    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        _create_context_ready_user(uow.session, "legacy-refresh-user")
        uow.session.execute(
            TrainingPlanModel.__table__.update()
            .where(TrainingPlanModel.id == "plan-legacy-refresh-user")
            .values(
                starts_on=previous_ends_on - timedelta(days=27),
                ends_on=previous_ends_on,
            )
        )
        uow.session.execute(
            RaceModel.__table__.insert(),
            [
                {
                    "id": "legacy-completed-race",
                    "user_id": "legacy-refresh-user",
                    "name": "Completed Race",
                    "race_date": date(2027, 2, 1),
                    "distance_meters": 21097,
                    "status": "completed",
                    "metadata_json": {"priority": "primary"},
                },
                {
                    "id": "legacy-planned-race",
                    "user_id": "legacy-refresh-user",
                    "name": "Planned Race",
                    "race_date": date(2027, 2, 15),
                    "distance_meters": 21097,
                    "status": "planned",
                    "metadata_json": {"priority": "secondary"},
                },
            ],
        )
        queued = QueueAgentRunHandler(
            runs=SqlAlchemyAgentRunRepository(uow.session),
            queue=SqlAlchemyAgentTaskQueue(uow.session),
            prompt_version="running-companion-v1",
            provider="local",
            model="deterministic-local-companion",
        ).queue_run(
            user_id="legacy-refresh-user",
            workflow_name="training_plan_generation",
            trigger_type="scheduled",
            idempotency_key="training_plan_generation:legacy-refresh-user",
            payload={
                "race_id": "legacy-completed-race",
                "plan_type": "race",
                "starts_on": "2027-01-09",
                "plan_horizon_weeks": 4,
                "manual_regeneration": False,
                "trigger_type": "scheduled",
                "replace_active_projection": True,
            },
            requeue_terminal=True,
        )

        processed = work_drain(uow.session)
        refreshed_run = uow.session.get(AgentRunModel, queued.run.id)
        refreshed_task = uow.session.get(AgentTaskModel, queued.task.id)
        generated_plan = uow.session.scalar(
            select(TrainingPlanModel).where(
                TrainingPlanModel.user_id == "legacy-refresh-user",
                TrainingPlanModel.status == "active",
            )
        )
        uow.commit()

    assert processed == 1
    assert refreshed_run.status == "completed"
    assert refreshed_run.metadata_json["previous_ends_on"] == previous_ends_on.isoformat()
    assert refreshed_run.metadata_json["starts_on"] == refreshed_starts_on.isoformat()
    assert refreshed_run.metadata_json["race_id"] == "legacy-planned-race"
    assert refreshed_task.payload["input"]["previous_ends_on"] == previous_ends_on.isoformat()
    assert refreshed_task.payload["input"]["starts_on"] == refreshed_starts_on.isoformat()
    assert generated_plan is not None
    assert generated_plan.starts_on == refreshed_starts_on
    assert generated_plan.race_id == "legacy-planned-race"


def test_work_drain_processes_daily_and_training_plan_generation_tasks(sqlite_session_factory) -> None:
    Base.metadata.create_all(sqlite_session_factory.kw["bind"])
    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        _create_context_ready_user(uow.session, "worker-user")
        handler_runs = SqlAlchemyAgentRunRepository(uow.session)
        queue = SqlAlchemyAgentTaskQueue(uow.session)
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
        generated_plan = uow.session.scalar(
            select(TrainingPlanModel).where(
                TrainingPlanModel.user_id == "worker-user",
                TrainingPlanModel.name == "Local Generated Skeleton Plan",
            )
        )
        recommendation_count = len(uow.session.scalars(select(RecommendationModel)).all())
        uow.commit()

    assert processed == 2
    assert daily_run.status == "completed"
    assert training_run.status == "completed"
    assert generated_plan is not None
    assert generated_plan.status == "active"
    assert generated_plan.metadata_json["phase_segments"] == [
        {"phase": "maintenance", "starts_on": "2027-01-01", "ends_on": "2027-01-28"}
    ]
    assert {workout.details["phase"] for workout in generated_plan.workouts} == {"maintenance"}
    assert recommendation_count == 1


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
                task_type="training-plan.daily-check",
                payload={},
                correlation_id="daily-check-malformed",
                idempotency_key="daily-check-malformed",
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
        tasks = list(uow.session.scalars(select(AgentTaskModel).order_by(AgentTaskModel.created_at)))
        statuses = [task.status for task in tasks]
        errors = [task.last_error_type for task in tasks]
        retry_counts = [task.retry_count for task in tasks]
        uow.commit()

    assert processed == 3
    assert statuses == ["failed", "failed", "failed"]
    assert errors == ["UnknownTaskType", "MalformedTaskPayload", "MalformedTaskPayload"]
    assert retry_counts == [1, 1, 1]


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
    assert len(recommendations) == 1
    assert any(plan["name"] == "Local Generated Skeleton Plan" and plan["status"] == "active" for plan in plans)
