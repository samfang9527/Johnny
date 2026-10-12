from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import logging
import sys

import pytest

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
from src.domain.agent_runtime import ModelResponse, ToolCallRequest
from src.domain.daily_advice import AdviceSections, DailyAdvice, RefreshVersion, WeekExecution, WorkoutGuide
from src.application.training_plan_regeneration import BackgroundProjectionCandidate, RegenerationStrategy
from src.api.dependencies import get_session
from src.application.interfaces.task_queue import TaskEnvelope
from src.api.dependencies import CurrentUser, ensure_current_user
from src.infrastructure.database.agent_run_repository import SqlAlchemyAgentRunRepository
from src.infrastructure.database.agent_task_queue import SqlAlchemyAgentTaskQueue
from src.infrastructure.database.daily_advice_repository import SqlAlchemyDailyAdviceRepository
from src.infrastructure.database.integration_repository import SqlAlchemyIntegrationRepository
from src.infrastructure.database.models import (
    AgentRunModel,
    AgentTaskModel,
    ActivityModel,
    Base,
    DailyAdviceModel,
    IntegrationConnectionModel,
    RaceModel,
    RecommendationModel,
    TrainingPlanModel,
    UserModel,
    WorkoutModel,
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
    assert len(daily_tasks) == 0
    assert len([task for task in tasks if task.task_type == "daily_advice.sync"]) == 2
    assert {task.payload["input"]["anchor_date"] for task in tasks if task.task_type == "daily_advice.sync"} == {"2027-01-28"}
    assert len(daily_check_tasks) == 1
    assert daily_check_tasks[0].payload == {"anchor_date": "2027-01-28"}


def test_scheduled_daily_run_waits_for_sync_gate_then_uses_stored_data_without_connection(sqlite_session_factory) -> None:
    Base.metadata.create_all(sqlite_session_factory.kw["bind"])
    day = date.today()
    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        _create_context_ready_user(uow.session, "no-connection-user")
        plan = uow.session.get(TrainingPlanModel, "plan-no-connection-user")
        plan.starts_on = day - timedelta(days=3)
        plan.ends_on = day + timedelta(days=14)
        uow.session.add(ActivityModel(
            id="stored-run", user_id="no-connection-user",
            started_at=datetime.combine(day, datetime.min.time(), tzinfo=timezone.utc),
            activity_type="run", distance_meters=5000, duration_seconds=1800,
            provider_summary={},
        ))
        assert schedule_once(uow.session, anchor_date=day) == 2
        tasks = list(uow.session.scalars(select(AgentTaskModel).where(AgentTaskModel.task_type == "daily_advice.sync")))
        run_id = tasks[0].payload["run_id"]

        assert work_drain(uow.session, max_tasks=1) == 1
        assert uow.session.scalar(select(DailyAdviceModel).where(DailyAdviceModel.user_id == "no-connection-user")) is None
        generation = uow.session.scalar(select(AgentTaskModel).where(AgentTaskModel.task_type == "agent.workflow"))
        assert generation is not None
        assert generation.payload["run_id"] == run_id
        assert generation.payload["input"]["source_sync_run_id"] is None

        assert work_drain(uow.session) == 2
        advice = uow.session.scalar(select(DailyAdviceModel).where(DailyAdviceModel.user_id == "no-connection-user"))
        uow.commit()

    assert advice.state == "ready"
    assert advice.data_freshness == "limited"
    assert advice.facts["actual_minutes"] == 30


class _WorkerGarminAdapter:
    def __init__(self, *, fail_activities: bool = False, fail_health: bool = False) -> None:
        self.fail_activities = fail_activities
        self.fail_health = fail_health
        self.calls = []

    def fetch_resource(self, *, connection, resource_type, start_date, end_date, timezone_name, cursor):
        from src.application.integrations import GarminResourceFetchResult

        self.calls.append(resource_type)
        if resource_type == "activities" and self.fail_activities:
            raise RuntimeError("activities unavailable")
        if resource_type == "sleep" and self.fail_health:
            raise RuntimeError("sleep unavailable")
        if resource_type == "activities":
            return GarminResourceFetchResult(items=[{
                "activityId": "worker-run-1", "activityType": {"typeKey": "running"},
                "startTimeGMT": f"{end_date.isoformat()} 00:00:00", "distance": 5000, "duration": 1800,
            }])
        return GarminResourceFetchResult()


@pytest.mark.parametrize(
    ("fail_activities", "fail_health", "expected_state", "expected_freshness"),
    [
        (False, False, "ready", "fresh"),
        (False, True, "ready", "limited"),
        (True, False, "sync_failed", "limited"),
    ],
)
def test_scheduled_sync_imports_before_generation_and_gates_activity_failures(
    sqlite_session_factory, monkeypatch, fail_activities, fail_health, expected_state, expected_freshness,
) -> None:
    adapter = _WorkerGarminAdapter(fail_activities=fail_activities, fail_health=fail_health)
    monkeypatch.setattr(agent_runtime, "_build_garmin_sync_adapter", lambda session, integrations: adapter)
    Base.metadata.create_all(sqlite_session_factory.kw["bind"])
    day = date.today()
    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        _create_context_ready_user(uow.session, "connected-worker")
        plan = uow.session.get(TrainingPlanModel, "plan-connected-worker")
        plan.starts_on = day - timedelta(days=3)
        plan.ends_on = day + timedelta(days=14)
        uow.session.add(WorkoutModel(
            id="connected-workout", training_plan_id=plan.id, scheduled_for=day,
            workout_type="easy_run", planned_duration_minutes=30, status="planned",
            details={"purpose": "建立有氧基礎"},
        ))
        SqlAlchemyIntegrationRepository(uow.session).create_connection(
            user_id="connected-worker", provider="garmin_connect", provider_account_id="connected-garmin",
        )
        assert schedule_once(uow.session, anchor_date=day) == 2
        assert work_drain(uow.session, max_tasks=1) == 1
        assert uow.session.scalar(select(DailyAdviceModel).where(DailyAdviceModel.user_id == "connected-worker")) is None or fail_activities
        generation = uow.session.scalar(select(AgentTaskModel).where(AgentTaskModel.task_type == "agent.workflow"))
        assert (generation is not None) is (not fail_activities)
        if not fail_activities:
            assert generation.payload["input"]["source_sync_run_id"] is not None
            assert work_drain(uow.session) == 2
            generated_run = uow.session.get(AgentRunModel, generation.payload["run_id"])
            if fail_health:
                assert generated_run.metadata_json["limited_recovery"] is True
        advice = uow.session.scalar(select(DailyAdviceModel).where(DailyAdviceModel.user_id == "connected-worker"))
        uow.commit()

    assert adapter.calls[0] == "activities"
    assert advice.state == expected_state
    assert advice.data_freshness == expected_freshness
    if not fail_activities:
        assert advice.facts["actual_minutes"] == 30
        assert advice.source_sync_run_id is not None


def test_running_garmin_sync_defers_daily_generation_without_starting_second_sync(sqlite_session_factory, monkeypatch) -> None:
    adapter = _WorkerGarminAdapter()
    monkeypatch.setattr(agent_runtime, "_build_garmin_sync_adapter", lambda session, integrations: adapter)
    Base.metadata.create_all(sqlite_session_factory.kw["bind"])
    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        _create_context_ready_user(uow.session, "busy-worker")
        connection = SqlAlchemyIntegrationRepository(uow.session).create_connection(
            user_id="busy-worker", provider="garmin_connect", provider_account_id="busy-garmin",
        )
        SqlAlchemyIntegrationRepository(uow.session).start_sync_run(connection.id)
        schedule_once(uow.session, anchor_date=date(2027, 1, 28))
        assert work_drain(uow.session, max_tasks=1) == 1
        sync_task = uow.session.scalar(select(AgentTaskModel).where(AgentTaskModel.task_type == "daily_advice.sync"))
        assert sync_task.status == "queued"
        assert sync_task.available_at.replace(tzinfo=timezone.utc) > datetime.now(timezone.utc)
        assert uow.session.scalar(select(AgentTaskModel).where(AgentTaskModel.task_type == "agent.workflow")) is None
        assert uow.session.scalar(select(DailyAdviceModel).where(DailyAdviceModel.user_id == "busy-worker")) is None
        uow.commit()

    assert adapter.calls == []


def test_worker_exposes_running_sync_before_provider_fetch(tmp_path, monkeypatch) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'sync-visible.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    with session_factory() as session:
        _create_context_ready_user(session, "visible-worker")
        SqlAlchemyIntegrationRepository(session).create_connection(
            user_id="visible-worker", provider="garmin_connect", provider_account_id="visible-garmin",
        )
        schedule_once(session, anchor_date=date(2027, 1, 28))
        session.commit()

    class InspectAdapter(_WorkerGarminAdapter):
        def fetch_resource(self, **kwargs):
            if not self.calls:
                with session_factory() as observer:
                    observed = observer.scalar(select(IntegrationConnectionModel.sync_status))
                    assert observed == "running"
            return super().fetch_resource(**kwargs)

    adapter = InspectAdapter()
    monkeypatch.setattr(agent_runtime, "_build_garmin_sync_adapter", lambda session, integrations: adapter)
    with session_factory() as session:
        assert work_drain(session, max_tasks=1) == 1
        task = session.scalar(select(AgentTaskModel).where(AgentTaskModel.task_type == "daily_advice.sync"))
        assert task.status == "completed"


def test_scheduled_reauth_blocks_generation_and_marks_existing_advice_sync_failed(sqlite_session_factory, monkeypatch) -> None:
    adapter = _WorkerGarminAdapter()
    monkeypatch.setattr(agent_runtime, "_build_garmin_sync_adapter", lambda session, integrations: adapter)
    Base.metadata.create_all(sqlite_session_factory.kw["bind"])
    day = date(2027, 1, 28)
    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        _create_context_ready_user(uow.session, "reauth-worker")
        connection = SqlAlchemyIntegrationRepository(uow.session).create_connection(
            user_id="reauth-worker", provider="garmin_connect", provider_account_id="reauth-garmin",
        )
        model = uow.session.get(IntegrationConnectionModel, connection.id)
        model.credential_status = "requires_reauth"
        advice_store = SqlAlchemyDailyAdviceRepository(uow.session)
        previous = RefreshVersion(datetime(2026, 1, 1, tzinfo=timezone.utc), "previous-run")
        assert advice_store.begin_refresh("reauth-worker", day, previous, None)
        assert advice_store.publish("reauth-worker", day, previous, DailyAdvice(
            user_id="reauth-worker", advice_date=day, plan_version_id="plan-reauth-worker",
            workout_id=None, week_start=date(2027, 1, 22), week_end=day, execution_mode="rest",
            facts=WeekExecution(
                week_start=date(2027, 1, 22), week_end=day, status="on_plan",
                planned_count=0, completed_count=0, missed_count=0, extra_count=0,
                planned_minutes=None, actual_minutes=0, planned_distance_meters=None,
                actual_distance_meters=0, today_completed=False,
            ),
            sections=AdviceSections("先前建議", "今天休息", WorkoutGuide("恢復", "輕鬆", "休息", "維持休息")),
            generated_at=datetime(2026, 1, 1, tzinfo=timezone.utc), source_sync_run_id=None,
            source_run_id="previous-run", state="ready", data_freshness="limited",
        ))
        schedule_once(uow.session, anchor_date=day)
        assert work_drain(uow.session, max_tasks=1) == 1
        assert uow.session.scalar(select(AgentTaskModel).where(AgentTaskModel.task_type == "agent.workflow")) is None
        advice = uow.session.scalar(select(DailyAdviceModel).where(DailyAdviceModel.user_id == "reauth-worker"))
        uow.commit()

    assert advice.state == "sync_failed"
    assert advice.week_summary == "先前建議"
    assert advice.data_freshness == "stale"
    assert adapter.calls == []


def test_manual_garmin_sync_queues_daily_refresh_with_import_in_same_response_transaction() -> None:
    from src.api.routes.integrations import get_garmin_resource_adapter, _queue_daily_advice_after_sync

    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    day = date.today()
    with session_factory() as session:
        _create_context_ready_user(session, "manual-sync-user")
        plan = session.get(TrainingPlanModel, "plan-manual-sync-user")
        plan.starts_on = day - timedelta(days=3)
        plan.ends_on = day + timedelta(days=14)
        connection = SqlAlchemyIntegrationRepository(session).create_connection(
            user_id="manual-sync-user", provider="garmin_connect", provider_account_id="manual-sync-garmin",
        )
        session.commit()

    def override_session():
        with session_factory() as session:
            yield session
            session.commit()

    app = create_app()
    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_garmin_resource_adapter] = lambda: _WorkerGarminAdapter()
    client = TestClient(app)
    response = client.post(
        f"/api/v1/integrations/connections/{connection.id}/sync",
        headers={"X-Johnny-User-Id": "manual-sync-user"},
    )

    assert response.status_code == 200
    refresh = response.json()["data"]["daily_advice_run"]
    assert refresh["workflow_name"] == "daily_recommendation"
    assert refresh["status"] == "queued"
    with session_factory() as session:
        tasks = list(session.scalars(select(AgentTaskModel).where(AgentTaskModel.task_type == "agent.workflow")))
        activities = list(session.scalars(select(ActivityModel).where(ActivityModel.user_id == "manual-sync-user")))
        assert len(tasks) == 1
        assert len(activities) == 1
        assert tasks[0].payload["run_id"] == refresh["run_id"]
        assert tasks[0].payload["input"]["source_sync_run_id"] is not None
        assert work_drain(session) == 1
        existing = _queue_daily_advice_after_sync(
            session, repository=SqlAlchemyIntegrationRepository(session), user_id="manual-sync-user",
            connection=SqlAlchemyIntegrationRepository(session).get_connection_for_user("manual-sync-user", connection.id),
        )
        assert existing.run_id == refresh["run_id"]
        assert len(list(session.scalars(select(AgentTaskModel).where(AgentTaskModel.task_type == "agent.workflow")))) == 1


def test_manual_daily_request_starts_with_sync_gate() -> None:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)

    def override_session():
        with session_factory() as session:
            yield session
            session.commit()

    app = create_app()
    app.dependency_overrides[get_session] = override_session
    client = TestClient(app)
    queued = client.post(
        "/api/v1/agent-runs/daily-recommendation",
        headers={"X-Johnny-User-Id": "manual-daily-user"},
        json={"anchor_date": "2027-01-28"},
    )
    assert queued.status_code == 200
    with session_factory() as session:
        task = session.scalar(select(AgentTaskModel).where(AgentTaskModel.payload["run_id"].as_string() == queued.json()["data"]["run_id"]))
        assert task.task_type == "daily_advice.sync"


def test_connect_and_token_import_each_queue_one_refresh_for_their_sync_run(tmp_path, monkeypatch) -> None:
    from src.api.routes.integrations import (
        get_garmin_credential_cipher, get_garmin_login_adapter, get_garmin_resource_adapter,
    )
    from src.application.integrations import GarminAccountProfile

    engine = create_engine(f"sqlite:///{tmp_path / 'connect-advice.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    day = date.today()
    with session_factory() as session:
        _create_context_ready_user(session, "connect-advice-user")
        plan = session.get(TrainingPlanModel, "plan-connect-advice-user")
        plan.starts_on = day - timedelta(days=3)
        plan.ends_on = day + timedelta(days=14)
        session.commit()

    def override_session():
        with session_factory() as session:
            yield session
            session.commit()

    class Login:
        def exchange_credentials(self, **kwargs):
            return GarminAccountProfile(
                provider_account_id="connect-advice-garmin", display_name="Runner",
                session_payload='{"oauth2_token":"secret"}',
            )

    class Cipher:
        key_id = "test-key"

        def encrypt(self, plaintext):
            return "fernet:encrypted-session"

    app = create_app()
    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_garmin_credential_cipher] = lambda: Cipher()
    app.dependency_overrides[get_garmin_login_adapter] = lambda: Login()
    app.dependency_overrides[get_garmin_resource_adapter] = lambda: _WorkerGarminAdapter()
    client = TestClient(app)
    headers = {"X-Johnny-User-Id": "connect-advice-user"}
    connected = client.post(
        "/api/v1/integrations/garmin/connect", headers=headers,
        json={"email": "runner@example.com", "password": "password", "region": "global"},
    )
    assert connected.status_code == 200
    connection_id = connected.json()["data"]["id"]
    first = connected.json()["data"]["daily_advice_run"]
    assert first["workflow_name"] == "daily_recommendation"

    monkeypatch.setenv("JOHNNY_ADMIN_TOKEN", "admin-secret")
    imported = client.post(
        f"/api/v1/integrations/connections/{connection_id}/admin-token-import",
        headers={**headers, "X-Johnny-Admin-Token": "admin-secret"},
        json={"session_payload": '{"oauth2_token":"renewed"}'},
    )
    assert imported.status_code == 200
    second = imported.json()["data"]["daily_advice_run"]
    assert second["run_id"] != first["run_id"]
    with session_factory() as session:
        tasks = list(session.scalars(select(AgentTaskModel).where(AgentTaskModel.task_type == "agent.workflow")))
        assert len(tasks) == 2
        assert {task.payload["run_id"] for task in tasks} == {first["run_id"], second["run_id"]}
        assert tasks[0].payload["input"]["source_sync_run_id"] != tasks[1].payload["input"]["source_sync_run_id"]
        SqlAlchemyIntegrationRepository(session).start_sync_run(connection_id)
        session.commit()

    blocked_import = client.post(
        f"/api/v1/integrations/connections/{connection_id}/admin-token-import",
        headers={**headers, "X-Johnny-Admin-Token": "admin-secret"},
        json={"session_payload": '{"oauth2_token":"again"}'},
    )
    blocked_connect = client.post(
        "/api/v1/integrations/garmin/connect", headers=headers,
        json={"email": "runner@example.com", "password": "password", "region": "global"},
    )
    assert blocked_import.status_code == 409
    assert blocked_connect.status_code == 409


def test_scheduler_training_plan_queue_uses_resolved_provider(sqlite_session_factory, monkeypatch) -> None:
    Base.metadata.create_all(sqlite_session_factory.kw["bind"])
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("LLM_MODEL", "test-model")
    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        ensure_current_user(uow.session, CurrentUser(id="scheduled-provider-user"))
        handler = agent_runtime._training_plan_queue_handler(uow.session)
        result = handler.queue_run(
            user_id="scheduled-provider-user",
            workflow_name="training_plan_generation",
            trigger_type="scheduled",
            idempotency_key="scheduled-provider-test",
            payload={"plan_type": "base", "starts_on": "2027-01-01"},
        )
        uow.commit()

    assert (result.run.provider, result.run.model) == ("openai", "test-model")


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


def test_work_drain_processes_daily_and_training_plan_generation_tasks(sqlite_session_factory, caplog) -> None:
    Base.metadata.create_all(sqlite_session_factory.kw["bind"])
    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        _create_context_ready_user(uow.session, "worker-user")
        uow.session.add(WorkoutModel(
            id="worker-original-workout", training_plan_id="plan-worker-user",
            scheduled_for=date(2027, 1, 28), workout_type="easy_run",
            planned_duration_minutes=40, status="planned", details={"purpose": "建立有氧基礎"},
        ))
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
            payload={"plan_type": "base", "starts_on": "2027-01-01", "goal_notes": "private-runner-note"},
        )

        with caplog.at_level(logging.INFO, logger="scripts.agent_runtime"):
            processed = work_drain(uow.session)
        daily_run = handler_runs.get_run_for_user("worker-user", daily.run.id)
        training_run = handler_runs.get_run_for_user("worker-user", training.run.id)
        generated_plan = uow.session.scalar(
            select(TrainingPlanModel).where(
                TrainingPlanModel.user_id == "worker-user",
                TrainingPlanModel.name == "Johnny 訓練計畫",
            )
        )
        recommendation_count = len(uow.session.scalars(select(RecommendationModel)).all())
        advice = uow.session.scalar(select(DailyAdviceModel).where(DailyAdviceModel.user_id == "worker-user"))
        original_workout = uow.session.get(WorkoutModel, "worker-original-workout")
        daily_steps = handler_runs.list_steps_for_run(daily.run.id)
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
    assert recommendation_count == 0
    assert advice is not None
    assert advice.state == "ready"
    assert advice.week_summary and advice.today_execution and advice.workout_guide
    assert advice.workout_id == "worker-original-workout"
    assert (original_workout.planned_duration_minutes, original_workout.status) == (40, "planned")
    assert daily_run.recommendation_id is None
    assert daily_run.metadata["daily_advice_id"] == advice.id
    assert daily_run.total_tokens == 0
    assert [(step.name, step.status) for step in daily_steps] == [("composeDailyAdvice", "completed")]
    assert "worker task claimed task_id=" in caplog.text
    assert f"worker workflow started run_id={training.run.id} workflow=training_plan_generation provider=local" in caplog.text
    assert f"worker workflow finished run_id={training.run.id} workflow=training_plan_generation status=completed" in caplog.text
    assert "worker task finished task_id=" in caplog.text
    assert "duration_ms=" in caplog.text
    assert "private-runner-note" not in caplog.text


def test_invalid_daily_model_output_fails_refresh_and_preserves_previous_advice(sqlite_session_factory, monkeypatch) -> None:
    class InvalidGateway:
        def complete(self, request):
            assert request.tools == ("composeDailyAdvice",)
            return ModelResponse(
                content="", tool_calls=(ToolCallRequest("composeDailyAdvice", {"week_summary": ""}),),
                provider="local", model="bad-local",
            )

    monkeypatch.setattr(agent_runtime, "LocalCompanionModelGateway", InvalidGateway)
    Base.metadata.create_all(sqlite_session_factory.kw["bind"])
    day = date(2027, 1, 28)
    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        _create_context_ready_user(uow.session, "invalid-advice-user")
        advice_store = SqlAlchemyDailyAdviceRepository(uow.session)
        old_version = RefreshVersion(datetime(2026, 1, 27, tzinfo=timezone.utc), "old-run")
        assert advice_store.begin_refresh("invalid-advice-user", day, old_version, None)
        assert advice_store.publish("invalid-advice-user", day, old_version, DailyAdvice(
            user_id="invalid-advice-user", advice_date=day, plan_version_id="plan-invalid-advice-user",
            workout_id=None, week_start=date(2027, 1, 22), week_end=day,
            execution_mode="rest", facts=WeekExecution(
                week_start=date(2027, 1, 22), week_end=day, status="on_plan",
                planned_count=0, completed_count=0, missed_count=0, extra_count=0,
                planned_minutes=None, actual_minutes=0, planned_distance_meters=None,
                actual_distance_meters=0, today_completed=False,
            ), sections=AdviceSections(
                week_summary="先前有效建議", today_execution="今天休息",
                workout_guide=WorkoutGuide("恢復", "輕鬆", "休息", "維持休息"),
            ), generated_at=datetime(2027, 1, 27, tzinfo=timezone.utc),
            source_sync_run_id=None, source_run_id="old-run", state="ready", data_freshness="limited",
        ))
        queued = QueueAgentRunHandler(
            runs=SqlAlchemyAgentRunRepository(uow.session), queue=SqlAlchemyAgentTaskQueue(uow.session),
            prompt_version="running-companion-v1", provider="local", model="deterministic-local-companion",
        ).queue_run(
            user_id="invalid-advice-user", workflow_name="daily_recommendation", trigger_type="manual",
            idempotency_key="invalid-daily-refresh", payload={"anchor_date": day.isoformat()},
        )
        assert work_drain(uow.session) == 1
        current = advice_store.get_for_user_date("invalid-advice-user", day)
        run_store = SqlAlchemyAgentRunRepository(uow.session)
        run = run_store.get_run_for_user("invalid-advice-user", queued.run.id)
        steps = run_store.list_steps_for_run(queued.run.id)
        uow.commit()

    assert run.status == "failed"
    assert run.recommendation_id is None
    assert current.state == "generation_failed"
    assert current.data_freshness == "stale"
    assert current.sections.week_summary == "先前有效建議"
    assert current.source_run_id == "old-run"
    assert [(step.name, step.status) for step in steps] == [("composeDailyAdvice", "failed")]


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


def test_agent_runtime_cli_worker_preserves_provider_environment(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setattr(
        sys, "argv",
        ["agent_runtime.py", "--database-url", f"sqlite:///{tmp_path / 'worker.db'}", "work-drain"],
    )

    assert main() == 0
    import os
    assert os.environ["LLM_PROVIDER"] == "openai"


def test_worker_uses_queued_local_provider_with_openai_environment(sqlite_session_factory, monkeypatch) -> None:
    from src.api.dependencies import build_request_companion_agent
    from src.infrastructure.llm.local_gateway import LocalCompanionModelGateway

    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("LLM_MODEL", "changed-model")
    with sqlite_session_factory() as session:
        agent = build_request_companion_agent(session, provider="local", model="deterministic-local-companion")
    assert isinstance(agent._model_gateway, LocalCompanionModelGateway)


def test_worker_uses_queued_openai_model_not_current_environment(sqlite_session_factory, monkeypatch) -> None:
    from src.api import dependencies

    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("LLM_MODEL", "changed-model")
    seen = []
    monkeypatch.setattr(dependencies, "build_running_companion_agent", lambda **kwargs: seen.append(kwargs["settings"]) or object())
    with sqlite_session_factory() as session:
        dependencies.build_request_companion_agent(session, provider="openai", model="queued-model")
    assert len(seen) == 1
    assert seen[0].model == "queued-model"


def test_worker_fails_queued_openai_run_without_key(sqlite_session_factory, monkeypatch, caplog) -> None:
    Base.metadata.create_all(sqlite_session_factory.kw["bind"])
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        ensure_current_user(uow.session, CurrentUser(id="missing-worker-key"))
        queued = QueueAgentRunHandler(
            runs=SqlAlchemyAgentRunRepository(uow.session),
            queue=SqlAlchemyAgentTaskQueue(uow.session),
            prompt_version="running-companion-v1", provider="openai", model="queued-model",
        ).queue_run(
            user_id="missing-worker-key", workflow_name="training_plan_generation",
            trigger_type="manual", idempotency_key="missing-worker-key",
            payload={"plan_type": "base", "starts_on": "2027-01-01"},
        )
        with caplog.at_level(logging.INFO, logger="scripts.agent_runtime"):
            assert work_drain(uow.session) == 1
        run = uow.session.get(AgentRunModel, queued.run.id)
        task = uow.session.scalar(select(AgentTaskModel).where(AgentTaskModel.payload["run_id"].as_string() == run.id))
        assert run.status == "failed"
        assert task.status == "failed"
        assert run.provider == "openai"
        assert "required" in run.error_message
        assert f"worker workflow started run_id={run.id} workflow=training_plan_generation provider=openai" in caplog.text
        assert f"worker workflow raised run_id={run.id} workflow=training_plan_generation error_type=" in caplog.text
        assert "status=failed" in caplog.text
        assert "OPENAI_API_KEY" not in caplog.text


def test_worker_rejects_unknown_persisted_provider(sqlite_session_factory) -> None:
    from src.api.dependencies import build_request_companion_agent

    with sqlite_session_factory() as session:
        try:
            build_request_companion_agent(session, provider="other", model="unknown")
        except ValueError as exc:
            assert "provider" in str(exc).lower()
        else:
            assert False, "unknown provider should fail"


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

    assert processed == 3
    assert daily_run["status"] == "completed"
    assert training_run["status"] == "completed"
    assert len(recommendations) == 0
    assert any(plan["name"] == "Johnny 訓練計畫" and plan["status"] == "active" for plan in plans)


def test_manual_regeneration_produces_race_aware_40km_projection(monkeypatch) -> None:
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
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
    today = date.today()
    race_day = today + timedelta(days=98)
    headers = {"X-Johnny-User-Id": "race-aware-runner"}
    with session_factory() as session:
        ensure_current_user(session, CurrentUser(id="race-aware-runner"))
        session.add(TrainingPlanModel(id="previous-race-plan", user_id="race-aware-runner", name="Old Plan", status="active", starts_on=today - timedelta(days=28), ends_on=today + timedelta(days=14), metadata_json={}))
        session.execute(Base.metadata.tables["athlete_profiles"].insert().values(id="race-aware-profile", user_id="race-aware-runner", timezone="UTC", experience_level="intermediate", metadata_json={"current_weekly_mileage_km": 25, "preferred_training_days": ["tuesday", "thursday", "sunday"], "preferred_long_run_day": "sunday", "max_runs_per_week": 3, "max_hard_sessions_per_week": 2}))
        session.add(RaceModel(id="race-40km", user_id="race-aware-runner", name="山徑 40K", race_date=race_day, distance_meters=40_000, status="planned", metadata_json={"priority": "primary", "terrain_difficulty": "technical", "ascent_meters": 1400, "goal_intent": "complete"}))
        completed_end = today - timedelta(days=today.weekday() + 1)
        for week in range(4):
            for run in range(2):
                day = completed_end - timedelta(days=27 - week * 7 - run * 2)
                session.add(ActivityModel(id=f"race-run-{week}-{run}", user_id="race-aware-runner", started_at=datetime.combine(day, datetime.min.time(), tzinfo=timezone.utc) + timedelta(hours=7), activity_type="run", distance_meters=12_500, duration_seconds=4500, provider_summary={}))
        session.commit()

    queued = client.post("/api/v1/training-plans/regenerations", headers=headers, json={"client_request_id": "race-aware-40km", "race_id": "race-40km", "plan_type": "race"})
    assert queued.status_code == 200, queued.text
    with session_factory() as session:
        assert work_drain(session) == 1
        session.commit()
    plans_response = client.get("/api/v1/training-plans", headers=headers)
    assert plans_response.status_code == 200
    plans = plans_response.json()["data"]
    active = next(plan for plan in plans if plan["status"] == "active")
    previous = next(plan for plan in plans if plan["id"] == "previous-race-plan")
    assert previous["status"] == "superseded"
    assert active["metadata"]["workload_policy_version"] == "race-workload-v2"
    assert active["preparation_assessment"]["status"] == "gap"
    assert max(workout["planned_duration_minutes"] for workout in active["workouts"] if workout["workout_type"] == "long_run") > 70
    assert all(workout["steps"] for workout in active["workouts"])
    assert "internal" not in active["metadata"]


def test_invalid_profile_at_worker_time_keeps_previous_projection_active(monkeypatch) -> None:
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
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
    today = date.today()
    headers = {"X-Johnny-User-Id": "invalid-profile-runner"}
    with session_factory() as session:
        ensure_current_user(session, CurrentUser(id="invalid-profile-runner"))
        session.add(TrainingPlanModel(id="safe-prior-plan", user_id="invalid-profile-runner", name="Current Plan", status="active", starts_on=today - timedelta(days=14), ends_on=today + timedelta(days=14), metadata_json={}))
        session.execute(Base.metadata.tables["athlete_profiles"].insert().values(id="valid-then-invalid", user_id="invalid-profile-runner", timezone="UTC", experience_level="intermediate", metadata_json={"current_weekly_mileage_km": 25, "max_runs_per_week": 3, "max_hard_sessions_per_week": 2}))
        session.add(RaceModel(id="later-race", user_id="invalid-profile-runner", name="40K", race_date=today + timedelta(days=84), distance_meters=40_000, status="planned", metadata_json={"priority": "primary"}))
        session.commit()

    queued = client.post("/api/v1/training-plans/regenerations", headers=headers, json={"client_request_id": "invalid-after-queue", "race_id": "later-race", "plan_type": "race"})
    assert queued.status_code == 200, queued.text
    with session_factory() as session:
        session.execute(Base.metadata.tables["athlete_profiles"].update().where(Base.metadata.tables["athlete_profiles"].c.id == "valid-then-invalid").values(metadata_json={"current_weekly_mileage_km": 25, "max_runs_per_week": 0}))
        session.commit()
    with session_factory() as session:
        assert work_drain(session) == 1
        session.commit()
    with session_factory() as session:
        active_ids = list(session.scalars(select(TrainingPlanModel.id).where(TrainingPlanModel.user_id == "invalid-profile-runner", TrainingPlanModel.status == "active")))
    assert active_ids == ["safe-prior-plan"]
