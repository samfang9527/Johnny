from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from src.api.dependencies import get_session
from src.application.coaching_refresh import CoachingRefreshService
from src.application.async_agent_runs import QueueAgentRunHandler
from src.domain.integrations_notifications import SyncSummary
from src.infrastructure.database.coaching_repository import SqlAlchemyCoachingRepository
from src.infrastructure.database.agent_run_repository import SqlAlchemyAgentRunRepository
from src.infrastructure.database.agent_task_queue import SqlAlchemyAgentTaskQueue
from src.infrastructure.database.models import AgentRunModel, AgentTaskModel, WorkoutAdviceModel
from tests.unit.api_test_helpers import create_sqlite_test_client


def test_pairing_change_corrects_only_affected_review_and_stales_advice():
    client = create_sqlite_test_client()
    headers = {"X-Johnny-User-Id": "refresh-athlete"}
    assert client.get("/api/v1/johnny/overview", headers=headers).status_code == 200
    scope = client.app.dependency_overrides[get_session]()
    session = next(scope)
    today = datetime.now(timezone.utc).date()
    store = SqlAlchemyCoachingRepository(session)
    review = store.reserve_review("refresh-athlete", today, "UTC", "review-run")
    assert store.publish_review(review, {"narrative": "R1", "coverage": {"covered_dates": []}})
    old = store.reserve_review("refresh-athlete", today - timedelta(days=10), "UTC", "old-run")
    assert store.publish_review(old, {"narrative": "Older review"})
    advice = store.reserve_advice("refresh-athlete", today, "no-workout", "advice-run", {})
    assert store.publish_advice(advice, {"guidance": "A1"}, None)
    session.commit()

    effects = CoachingRefreshService(session).record_change(
        user_id="refresh-athlete", changed_dates={today - timedelta(days=2)},
        today=today, reason="activity_pairing_changed")
    session.commit()
    assert len(effects.review_run_ids) == 1
    assert len(effects.invalidated_advice_ids) == 1
    current = store.get_review_slot("refresh-athlete", today)
    assert current["current"]["narrative"] == "R1"
    assert current["freshness"] == "stale"
    assert store.get_review_slot("refresh-athlete", today - timedelta(days=10))["freshness"] == "current"
    advice_slot = store.get_advice_slot("refresh-athlete", today, "no-workout")
    assert advice_slot["current"]["guidance"] == "A1"
    assert advice_slot["freshness"] == "stale"
    tasks = session.scalars(select(AgentTaskModel)).all()
    assert [task.payload["workflow_name"] for task in tasks] == ["daily_review"]
    assert tasks[0].task_type == "coaching.sync"
    assert tasks[0].payload["input"]["revision_reason"] == "activity_pairing_changed"
    scope.close()


def test_noop_sync_does_not_invalidate_either_stream():
    client = create_sqlite_test_client()
    headers = {"X-Johnny-User-Id": "noop-athlete"}
    client.get("/api/v1/johnny/overview", headers=headers)
    scope = client.app.dependency_overrides[get_session]()
    session = next(scope)
    today = datetime.now(timezone.utc).date()
    store = SqlAlchemyCoachingRepository(session)
    review = store.reserve_review("noop-athlete", today, "UTC", "r1")
    store.publish_review(review, {"narrative": "R1", "coverage": {"covered_dates": []}})
    advice = store.reserve_advice("noop-athlete", today, "no-workout", "a1", {})
    store.publish_advice(advice, {"guidance": "A1"}, None)
    session.commit()
    effects = CoachingRefreshService(session).record_sync(
        user_id="noop-athlete", summary=SyncSummary.empty(), today=today,
        timezone_name="UTC")
    assert effects.review_run_ids == ()
    assert effects.invalidated_advice_ids == ()
    assert store.get_review_slot("noop-athlete", today)["freshness"] == "current"
    assert store.get_advice_slot("noop-athlete", today, "no-workout")["freshness"] == "current"
    scope.close()


def test_manual_sync_recovers_due_review_rejected_by_old_worker():
    client = create_sqlite_test_client()
    headers = {"X-Johnny-User-Id": "sync-recovery-athlete"}
    client.get("/api/v1/johnny/overview", headers=headers)
    scope = client.app.dependency_overrides[get_session]()
    session = next(scope)
    today = datetime.now(timezone.utc).date()
    tasks = SqlAlchemyAgentTaskQueue(session)
    runs = SqlAlchemyAgentRunRepository(session)
    queued = QueueAgentRunHandler(
        runs=runs, queue=tasks, prompt_version="johnny-coaching-v1",
        provider="local", model="deterministic-local-companion",
    ).queue_run(
        user_id="sync-recovery-athlete", workflow_name="daily_review", trigger_type="scheduled",
        idempotency_key=f"daily_review:sync-recovery-athlete:{today.isoformat()}",
        payload={"publication_date": today.isoformat(), "timezone_name": "UTC"},
        task_type="coaching.sync",
    )
    store = SqlAlchemyCoachingRepository(session)
    store.reserve_review("sync-recovery-athlete", today, "UTC", queued.run.id)
    failed_task = session.get(AgentTaskModel, queued.task.id)
    failed_task.status = "failed"
    failed_task.last_error_type = "UnknownTaskType"
    session.commit()

    effects = CoachingRefreshService(session).record_sync(
        user_id="sync-recovery-athlete", summary=SyncSummary.empty().record_stored("activities"),
        today=today, timezone_name="UTC",
    )
    session.commit()
    current = store.get_review_slot("sync-recovery-athlete", today)
    repaired = session.get(AgentTaskModel, queued.task.id)
    assert repaired.status == "queued"
    assert repaired.payload["run_id"] != queued.run.id
    assert current["reserved_run_id"] == repaired.payload["run_id"]
    assert session.get(AgentRunModel, queued.run.id).status == "failed"
    assert effects.review_run_ids == (repaired.payload["run_id"],)
    assert session.scalars(select(WorkoutAdviceModel).where(
        WorkoutAdviceModel.user_id == "sync-recovery-athlete")).all() == []
    scope.close()
