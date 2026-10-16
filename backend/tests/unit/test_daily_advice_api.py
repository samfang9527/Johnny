from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.api.dependencies import CurrentUser, ensure_current_user, get_session
from src.domain.daily_advice import AdviceSections, DailyAdvice, RefreshVersion, WeekExecution, WorkoutGuide
from src.infrastructure.database.daily_advice_repository import SqlAlchemyDailyAdviceRepository
from src.infrastructure.database.models import AgentTaskModel, Base, DailyAdviceModel, TrainingPlanModel
from src.main import create_app


DAY = date(2027, 1, 28)
HEADERS = {"X-Johnny-User-Id": "athlete"}


@pytest.fixture()
def api():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(dbapi_connection, connection_record) -> None:  # noqa: ANN001
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    def override_session():
        with factory() as session:
            try:
                yield session
                session.commit()
            except Exception:
                session.rollback()
                raise

    app = create_app()
    app.dependency_overrides[get_session] = override_session
    with TestClient(app) as client:
        yield client, factory
    engine.dispose()


def _ready_advice(user_id: str, day: date, run_id: str, *, freshness: str = "fresh") -> DailyAdvice:
    return DailyAdvice(
        user_id=user_id, advice_date=day, plan_version_id="plan-1", workout_id="workout-1",
        week_start=date(2027, 1, 22), week_end=DAY, execution_mode="ease_off",
        facts=WeekExecution(
            week_start=date(2027, 1, 22), week_end=DAY, status="above",
            planned_count=3, completed_count=4, missed_count=0, extra_count=1,
            planned_minutes=120, actual_minutes=180, planned_distance_meters=20000,
            actual_distance_meters=28000, today_completed=False,
        ),
        sections=AdviceSections(
            week_summary=f"Summary {run_id}", today_execution="Ease off today",
            workout_guide=WorkoutGuide("Aerobic base", "Comfortable", "Slow down", "Keep it easy"),
        ),
        generated_at=datetime(2027, 1, 28, 5, tzinfo=timezone.utc),
        source_sync_run_id="sync-1" if freshness == "fresh" else None,
        source_run_id=run_id, state="ready", data_freshness=freshness,
    )


def _seed_ready(session, user_id: str, day: date, run_id: str, *, freshness: str = "fresh") -> str:
    ensure_current_user(session, CurrentUser(id=user_id))
    store = SqlAlchemyDailyAdviceRepository(session)
    version = RefreshVersion(datetime(2027, 1, 28, 4, tzinfo=timezone.utc), run_id)
    sync_id = "sync-1" if freshness == "fresh" else None
    assert store.begin_refresh(user_id, day, version, sync_id)
    assert store.publish(user_id, day, version, _ready_advice(user_id, day, run_id, freshness=freshness))
    return store.get_for_user_date(user_id, day).id


def test_today_returns_one_date_scoped_advice_with_all_sections_and_keeps_recommendation(api) -> None:
    client, factory = api
    with factory() as session:
        advice_id = _seed_ready(session, "athlete", DAY, "run-1")
        _seed_ready(session, "athlete", DAY + timedelta(days=1), "run-next")
        _seed_ready(session, "other", DAY, "other-run")
        session.commit()
    recommendation = client.post("/api/v1/recommendations", headers=HEADERS, json={
        "recommendation_type": "informational", "priority": "medium", "title": "Review sleep",
        "rationale": "Sleep debt is high", "evidence": [{"source": "training_analytics", "metric": "sleep_debt", "value": 90}],
        "proposed_action": {"type": "no_plan_change", "reason": "Review recovery"},
    })
    assert recommendation.status_code == 200

    today = client.get(f"/api/v1/today?anchor_date={DAY}", headers=HEADERS)
    advice = today.json()["data"]["daily_advice"]
    assert today.status_code == 200
    assert advice["id"] == advice_id
    assert advice["advice_date"] == DAY.isoformat()
    assert advice["state"] == "ready"
    assert advice["data_freshness"] == "fresh"
    assert advice["generated_at"] == "2027-01-28T05:00:00Z"
    assert advice["plan_week"] == {"starts_on": "2027-01-22", "ends_on": "2027-01-28"}
    assert advice["execution_mode"] == "ease_off"
    assert advice["facts"]["status"] == "above"
    assert advice["week_summary"] == "Summary run-1"
    assert advice["today_execution"] == "Ease off today"
    assert advice["workout_guide"]["if_too_hard"] == "Slow down"
    assert today.json()["data"]["current_recommendation"]["title"] == "Review sleep"
    assert recommendation.json()["data"]["status"] == "pending"
    assert client.get("/api/v1/recommendations", headers=HEADERS).json()["data"][0]["id"] == recommendation.json()["data"]["id"]
    assert client.get(f"/api/v1/today?anchor_date={DAY + timedelta(days=1)}", headers=HEADERS).json()["data"]["daily_advice"]["source_run_id"] == "run-next"
    assert client.get(f"/api/v1/today?anchor_date={DAY}", headers={"X-Johnny-User-Id": "other"}).json()["data"]["daily_advice"]["source_run_id"] == "other-run"
    assert client.get(f"/api/v1/today?anchor_date={DAY - timedelta(days=1)}", headers=HEADERS).json()["data"]["daily_advice"] is None


@pytest.mark.parametrize("state", ["pending", "sync_failed", "generation_failed", "no_plan"])
def test_today_exposes_empty_advice_states_without_inventing_content(api, state) -> None:
    client, factory = api
    with factory() as session:
        ensure_current_user(session, CurrentUser(id="athlete"))
        store = SqlAlchemyDailyAdviceRepository(session)
        version = RefreshVersion(datetime(2027, 1, 28, 4, tzinfo=timezone.utc), "run-1")
        assert store.begin_refresh("athlete", DAY, version, None)
        if state != "pending":
            assert store.mark_failed("athlete", DAY, version, state)
        session.commit()

    advice = client.get(f"/api/v1/today?anchor_date={DAY}", headers=HEADERS).json()["data"]["daily_advice"]
    assert advice["state"] == state
    assert advice["data_freshness"] == "limited"
    assert advice["generated_at"] is None
    assert advice["plan_week"] is None
    assert advice["facts"] is None
    assert advice["week_summary"] is None
    assert advice["today_execution"] is None
    assert advice["workout_guide"] is None


@pytest.mark.parametrize("failed_state", ["sync_failed", "generation_failed", "no_plan"])
def test_today_preserves_prior_sections_after_failed_refresh(api, failed_state) -> None:
    client, factory = api
    with factory() as session:
        advice_id = _seed_ready(session, "athlete", DAY, "old-run", freshness="limited")
        store = SqlAlchemyDailyAdviceRepository(session)
        version = RefreshVersion(datetime(2027, 1, 28, 6, tzinfo=timezone.utc), "new-run")
        assert store.begin_refresh("athlete", DAY, version, None)
        assert store.mark_failed("athlete", DAY, version, failed_state)
        session.commit()

    advice = client.get(f"/api/v1/today?anchor_date={DAY}", headers=HEADERS).json()["data"]["daily_advice"]
    assert advice["id"] == advice_id
    assert advice["state"] == failed_state
    assert advice["data_freshness"] == "stale"
    assert advice["source_run_id"] == "old-run"
    assert advice["week_summary"] == "Summary old-run"
    assert advice["today_execution"] == "Ease off today"


def test_today_exposes_limited_ready_advice_and_stale_prior_content_during_refresh(api) -> None:
    client, factory = api
    with factory() as session:
        _seed_ready(session, "athlete", DAY, "old-run", freshness="limited")
        session.commit()
    ready = client.get(f"/api/v1/today?anchor_date={DAY}", headers=HEADERS).json()["data"]["daily_advice"]
    assert ready["state"] == "ready"
    assert ready["data_freshness"] == "limited"
    assert ready["source_sync_run_id"] is None

    with factory() as session:
        version = RefreshVersion(datetime(2027, 1, 28, 6, tzinfo=timezone.utc), "new-run")
        assert SqlAlchemyDailyAdviceRepository(session).begin_refresh("athlete", DAY, version, None)
        session.commit()
    pending = client.get(f"/api/v1/today?anchor_date={DAY}", headers=HEADERS).json()["data"]["daily_advice"]
    assert pending["state"] == "pending"
    assert pending["data_freshness"] == "stale"
    assert pending["source_run_id"] == "old-run"
    assert pending["week_summary"] == "Summary old-run"


def test_legacy_manual_endpoint_adapts_to_today_workout_advice_without_writing_old_advice(api) -> None:
    from scripts.agent_runtime import work_drain

    client, factory = api
    first = client.post("/api/v1/agent-runs/daily-recommendation", headers=HEADERS, json={})
    assert first.status_code == 202
    first_run = first.json()["data"]
    assert set(first_run) == {"run_id", "status", "workflow_name", "poll_url"}
    assert first_run["workflow_name"] == "workout_advice"
    with factory() as session:
        task = session.scalar(select(AgentTaskModel).where(AgentTaskModel.payload["run_id"].as_string() == first_run["run_id"]))
        assert task.task_type == "coaching.sync"
        assert work_drain(session) == 2
        session.commit()
    first_status = client.get(first_run["poll_url"], headers=HEADERS).json()["data"]
    today = datetime.now(timezone.utc).date()
    first_advice = client.get(f"/api/v1/today?anchor_date={today}", headers=HEADERS).json()["data"]["workout_advice"]
    assert first_status["workout_advice_id"] == first_advice["id"]
    assert first_status["recommendation_id"] is None
    assert client.get(f"/api/v1/today?anchor_date={today}", headers=HEADERS).json()["data"]["daily_advice"] is None
    second = client.post("/api/v1/agent-runs/daily-recommendation", headers=HEADERS, json={"force": True})
    assert second.status_code == 202
    assert second.json()["data"]["run_id"] != first_run["run_id"]
    with factory() as session:
        assert work_drain(session) == 2
        session.commit()
    second_status = client.get(second.json()["data"]["poll_url"], headers=HEADERS).json()["data"]
    second_advice = client.get(f"/api/v1/today?anchor_date={today}", headers=HEADERS).json()["data"]["workout_advice"]
    with factory() as session:
        assert session.scalar(select(DailyAdviceModel).where(DailyAdviceModel.user_id == "athlete")) is None
    assert second_advice["id"] == first_advice["id"]
    assert second_status["workout_advice_id"] == second_advice["id"]
    assert second_status["recommendation_id"] is None
