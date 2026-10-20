from datetime import date, datetime, timedelta, timezone

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
    assert tasks[0].task_type == "agent.workflow"
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


def test_today_health_change_does_not_correct_older_reviews():
    client = create_sqlite_test_client()
    headers = {"X-Johnny-User-Id": "dated-health-athlete"}
    client.get("/api/v1/johnny/overview", headers=headers)
    scope = client.app.dependency_overrides[get_session]()
    session = next(scope)
    today = date(2026, 10, 19)
    store = SqlAlchemyCoachingRepository(session)
    for publication_date in (date(2026, 10, 17), date(2026, 10, 18)):
        review = store.reserve_review("dated-health-athlete", publication_date, "Asia/Taipei", "initial-run")
        assert store.publish_review(review, {
            "narrative": "Earlier review",
            "coverage": {"covered_dates": [
                f"2026-10-{day:02d}" for day in range(10, publication_date.day)
            ]},
        })
    advice = store.reserve_advice("dated-health-athlete", today, "no-workout", "advice-run", {})
    assert store.publish_advice(advice, {"guidance": "Today's advice"}, None)
    session.commit()

    summary = SyncSummary.from_payload({
        "resources": {"stress": {"stored": 1}, "body_battery": {"stored": 1}},
        "stored_dates": {"stress": ["2026-10-19"], "body_battery": ["2026-10-19"]},
        "activity_coverage": {
            "starts_on": "2026-09-20", "ends_on": "2026-10-19",
            "timezone_name": "Asia/Taipei", "pagination_complete": True, "skipped_count": 0,
        },
    })
    effects = CoachingRefreshService(session).record_sync(
        user_id="dated-health-athlete", summary=summary, today=today,
        timezone_name="Asia/Taipei", exclude_review_date=today,
    )

    assert effects.review_run_ids == ()
    assert len(effects.invalidated_advice_ids) == 1
    assert session.scalars(select(AgentTaskModel)).all() == []
    for publication_date in (date(2026, 10, 17), date(2026, 10, 18)):
        assert store.get_review_slot("dated-health-athlete", publication_date)["freshness"] == "current"
    scope.close()


def test_prior_day_health_change_corrects_only_review_covering_that_date():
    client = create_sqlite_test_client()
    headers = {"X-Johnny-User-Id": "prior-health-athlete"}
    client.get("/api/v1/johnny/overview", headers=headers)
    scope = client.app.dependency_overrides[get_session]()
    session = next(scope)
    store = SqlAlchemyCoachingRepository(session)
    for publication_date in (date(2026, 10, 17), date(2026, 10, 18)):
        review = store.reserve_review("prior-health-athlete", publication_date, "Asia/Taipei", "initial-run")
        assert store.publish_review(review, {"narrative": "Earlier review"})
    session.commit()

    summary = SyncSummary.from_payload({
        "resources": {"stress": {"stored": 1}},
        "stored_dates": {"stress": ["2026-10-17"]},
    })
    effects = CoachingRefreshService(session).record_sync(
        user_id="prior-health-athlete", summary=summary, today=date(2026, 10, 19),
        timezone_name="Asia/Taipei",
    )

    assert len(effects.review_run_ids) == 1
    task = session.scalars(select(AgentTaskModel)).one()
    assert task.payload["input"]["publication_date"] == "2026-10-18"
    assert store.get_review_slot("prior-health-athlete", date(2026, 10, 17))["freshness"] == "current"
    scope.close()


def test_undated_evidence_change_keeps_conservative_review_correction():
    client = create_sqlite_test_client()
    headers = {"X-Johnny-User-Id": "undated-evidence-athlete"}
    client.get("/api/v1/johnny/overview", headers=headers)
    scope = client.app.dependency_overrides[get_session]()
    session = next(scope)
    store = SqlAlchemyCoachingRepository(session)
    review = store.reserve_review("undated-evidence-athlete", date(2026, 10, 18), "Asia/Taipei", "initial-run")
    assert store.publish_review(review, {"narrative": "Earlier review"})
    session.commit()

    effects = CoachingRefreshService(session).record_sync(
        user_id="undated-evidence-athlete",
        summary=SyncSummary.empty().record_stored("heart_rate_zones"),
        today=date(2026, 10, 19), timezone_name="Asia/Taipei",
    )

    assert len(effects.review_run_ids) == 1
    assert store.get_review_slot("undated-evidence-athlete", date(2026, 10, 18))["freshness"] == "stale"
    scope.close()


def test_old_activity_from_long_catch_up_corrects_its_historical_review():
    client = create_sqlite_test_client()
    headers = {"X-Johnny-User-Id": "old-activity-athlete"}
    client.get("/api/v1/johnny/overview", headers=headers)
    scope = client.app.dependency_overrides[get_session]()
    session = next(scope)
    today = date(2026, 10, 20)
    store = SqlAlchemyCoachingRepository(session)
    old_date = date(2026, 9, 3)
    reservation = store.reserve_review("old-activity-athlete", old_date, "Asia/Taipei", "prior-run")
    assert store.publish_review(reservation, {"narrative": "Before catch-up", "coverage": {
        "covered_dates": [f"2026-09-{day:02d}" for day in range(1, 3)],
    }})
    session.commit()

    summary = SyncSummary.from_payload({
        "resources": {"activities": {"stored": 1}},
        "stored_dates": {"activities": ["2026-09-02"]},
        "activity_coverage": {"starts_on": "2026-09-01", "ends_on": "2026-10-20",
                              "timezone_name": "Asia/Taipei", "pagination_complete": True},
    })
    effects = CoachingRefreshService(session).record_sync(
        user_id="old-activity-athlete", summary=summary, today=today,
        timezone_name="Asia/Taipei",
    )
    assert len(effects.review_run_ids) == 1
    assert store.get_review_slot("old-activity-athlete", old_date)["freshness"] == "stale"
    assert session.scalars(select(AgentTaskModel)).one().payload["input"]["publication_date"] == "2026-09-03"
    scope.close()


def test_old_coverage_from_long_catch_up_corrects_uncovered_review():
    client = create_sqlite_test_client()
    headers = {"X-Johnny-User-Id": "old-coverage-athlete"}
    client.get("/api/v1/johnny/overview", headers=headers)
    scope = client.app.dependency_overrides[get_session]()
    session = next(scope)
    old_date = date(2026, 9, 3)
    store = SqlAlchemyCoachingRepository(session)
    reservation = store.reserve_review("old-coverage-athlete", old_date, "Asia/Taipei", "prior-run")
    assert store.publish_review(reservation, {"narrative": "Coverage unknown", "coverage": {"covered_dates": []}})
    session.commit()

    effects = CoachingRefreshService(session).record_sync(
        user_id="old-coverage-athlete", today=date(2026, 10, 20), timezone_name="Asia/Taipei",
        summary=SyncSummary.from_payload({
            "resources": {"activities": {"stored": 0}},
            "activity_coverage": {"starts_on": "2026-09-01", "ends_on": "2026-10-20",
                                  "timezone_name": "Asia/Taipei", "pagination_complete": True},
        }),
    )
    assert len(effects.review_run_ids) == 1
    assert store.get_review_slot("old-coverage-athlete", old_date)["freshness"] == "stale"
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
