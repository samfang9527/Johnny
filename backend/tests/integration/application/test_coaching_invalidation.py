from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from src.api.dependencies import get_session
from src.application.coaching_refresh import CoachingRefreshService
from src.domain.integrations_notifications import SyncSummary
from src.infrastructure.database.coaching_repository import SqlAlchemyCoachingRepository
from src.infrastructure.database.models import AgentTaskModel
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
