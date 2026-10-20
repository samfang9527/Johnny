"""Exercise sync windows and checkpoints through the real persistence boundary."""

from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from src.api.dependencies import CurrentUser, ensure_current_user
from src.application.integrations import GarminInitialSyncCommand, GarminInitialSyncHandler, GarminResourceFetchResult
from src.infrastructure.database.activity_repository import SqlAlchemyActivityRepository
from src.infrastructure.database.athlete_race_repository import SqlAlchemyAthleteRaceRepository
from src.infrastructure.database.coaching_repository import SqlAlchemyCoachingRepository
from src.infrastructure.database.integration_repository import SqlAlchemyIntegrationRepository
from src.infrastructure.database.models import Base, IntegrationResourceCursorModel
from src.infrastructure.database.outbox_repository import SqlAlchemyOutboxRepository
from src.infrastructure.integrations.garmin_normalizer import (
    normalize_garmin_activity, normalize_garmin_daily_health, normalize_garmin_training_evidence,
)


class DatedGarminFeed:
    def __init__(self):
        self.requests = []
        self.failures = set()
        self.pagination_complete = True
        self.activities = []
        self.health = {}

    def fetch_resource(self, *, connection, resource_type, start_date, end_date, timezone_name, cursor):
        self.requests.append((resource_type, start_date, end_date))
        if resource_type in self.failures:
            raise RuntimeError("Resource unavailable")
        items = self.activities if resource_type == "activities" else self.health.get(resource_type, [])
        return GarminResourceFetchResult(
            items=items, pagination_complete=self.pagination_complete,
            cursor={"start_date": start_date.isoformat(), "end_date": end_date.isoformat()},
        )


@pytest.fixture
def sync_context(sqlite_session_factory):
    Base.metadata.create_all(sqlite_session_factory.kw["bind"])
    with sqlite_session_factory() as session:
        ensure_current_user(session, CurrentUser(id="incremental-athlete"))
        integrations = SqlAlchemyIntegrationRepository(session)
        connection = integrations.create_connection(
            user_id="incremental-athlete", provider="garmin_connect",
            provider_account_id="incremental-garmin", provider_metadata={"timezone": "Asia/Taipei"},
        )
        feed = DatedGarminFeed()
        handler = GarminInitialSyncHandler(
            integrations=integrations, activities=SqlAlchemyActivityRepository(session),
            outbox=SqlAlchemyOutboxRepository(session), garmin=feed,
            athlete_profiles=SqlAlchemyAthleteRaceRepository(session),
            normalize_activity=lambda user, connection, payload: normalize_garmin_activity(
                user_id=user, provider_connection_id=connection, payload=payload),
            normalize_health=lambda user, payload: normalize_garmin_daily_health(user_id=user, payload=payload),
            normalize_training_evidence=normalize_garmin_training_evidence,
        )

        def sync(day, **kwargs):
            # 04:00 Taipei is still the previous UTC date.
            instant = datetime.fromisoformat(f"{day}T04:00:00+08:00")
            result = handler.handle(GarminInitialSyncCommand(
                user_id="incremental-athlete", connection_id=connection.id, as_of=instant, **kwargs))
            session.commit()
            return result

        yield session, integrations, connection, feed, sync


def test_initial_import_then_daily_overlap_preserves_review_coverage(sync_context):
    session, _, _, feed, sync = sync_context
    initial = sync("2026-10-20")
    assert feed.requests[0] == ("activities", date(2026, 9, 21), date(2026, 10, 20))
    assert initial.activity_coverage["starts_on"] == "2026-09-21"

    feed.requests.clear()
    subsequent = sync("2026-10-21")
    assert all(start == date(2026, 10, 18) and end == date(2026, 10, 21)
               for _, start, end in feed.requests)
    assert subsequent.activity_coverage["starts_on"] == "2026-10-18"
    assert subsequent.activity_coverage["ends_on"] == "2026-10-21"
    assert SqlAlchemyCoachingRepository(session).covered_review_dates(
        "incremental-athlete", date(2026, 10, 14), date(2026, 10, 20), "Asia/Taipei",
        datetime.now(timezone.utc) + timedelta(minutes=1),
    ) == frozenset(date(2026, 10, day) for day in range(14, 21))


def test_failed_resource_catches_up_independently_without_truncating_long_gap(sync_context):
    _, _, _, feed, sync = sync_context
    sync("2026-09-01")
    feed.failures = {"sleep"}
    sync("2026-10-19")
    feed.failures.clear()
    feed.requests.clear()
    sync("2026-10-20")
    windows = {resource: (start, end) for resource, start, end in feed.requests}
    assert windows["activities"] == (date(2026, 10, 17), date(2026, 10, 20))
    assert windows["sleep"] == (date(2026, 8, 30), date(2026, 10, 20))


@pytest.mark.parametrize("incomplete", ["pagination", "invalid_activity"])
def test_incomplete_activity_import_keeps_last_successful_checkpoint(sync_context, incomplete):
    _, integrations, connection, feed, sync = sync_context
    sync("2026-10-10")
    previous = integrations.get_resource_cursor(connection.id, "activities")
    if incomplete == "pagination":
        feed.pagination_complete = False
    else:
        feed.activities = [{"invalid": "activity"}]
    summary = sync("2026-10-19")
    assert summary.activity_coverage["pagination_complete"] is False
    assert integrations.get_resource_cursor(connection.id, "activities") == previous
    feed.pagination_complete = True
    feed.activities = []
    feed.requests.clear()
    sync("2026-10-20")
    assert feed.requests[0] == ("activities", date(2026, 10, 8), date(2026, 10, 20))


def test_failed_first_resource_gets_initial_window_on_retry(sync_context):
    _, _, _, feed, sync = sync_context
    feed.failures = {"sleep"}
    sync("2026-10-19")
    feed.failures.clear()
    feed.requests.clear()
    sync("2026-10-20")
    windows = {resource: start for resource, start, _ in feed.requests}
    assert windows["activities"] == date(2026, 10, 17)
    assert windows["sleep"] == date(2026, 9, 21)


def test_explicit_backfill_refetches_thirty_days_then_returns_to_incremental(sync_context):
    _, _, _, feed, sync = sync_context
    sync("2026-10-19")
    feed.requests.clear()
    sync("2026-10-20", full_history=True)
    assert feed.requests[0] == ("activities", date(2026, 9, 21), date(2026, 10, 20))
    feed.requests.clear()
    sync("2026-10-21")
    assert feed.requests[0] == ("activities", date(2026, 10, 18), date(2026, 10, 21))


def test_legacy_checkpoint_and_same_day_repeat_use_local_overlap(sync_context):
    _, integrations, connection, feed, sync = sync_context
    integrations.upsert_resource_cursor(connection.id, "activities", {
        "start_date": "2026-09-20", "end_date": "2026-10-19",
    })
    sync("2026-10-20")
    assert feed.requests[0] == ("activities", date(2026, 10, 17), date(2026, 10, 20))
    feed.requests.clear()
    sync("2026-10-20")
    assert feed.requests[0] == ("activities", date(2026, 10, 17), date(2026, 10, 20))


def test_scheduled_review_corrects_older_reviews_without_syncing_again(sync_context, monkeypatch):
    import scripts.agent_runtime as runtime
    from src.application.async_agent_runs import QueueAgentRunHandler
    from src.infrastructure.database.agent_run_repository import SqlAlchemyAgentRunRepository
    from src.infrastructure.database.agent_task_queue import SqlAlchemyAgentTaskQueue
    from src.infrastructure.database.models import AgentRunModel, AgentTaskModel, SyncRunModel

    session, _, _, feed, _ = sync_context
    store = SqlAlchemyCoachingRepository(session)
    for day in (17, 18, 19):
        pub = date(2026, 10, day)
        reservation = store.reserve_review("incremental-athlete", pub, "Asia/Taipei", f"old-{day}")
        store.publish_review(reservation, {"narrative": "Old review", "coverage": {
            "covered_dates": [(pub - timedelta(days=n)).isoformat() for n in range(1, 8)],
        }})
    feed.health["stress"] = [{
        "calendarDate": "2026-10-16", "get_stress_data": {"avgStressLevel": 25},
    }]
    monkeypatch.setattr(runtime, "_build_garmin_sync_adapter", lambda session, integrations: feed)
    # Advance the queue clock past the correction debounce without sleeping.
    monkeypatch.setattr(runtime, "_utc_now", lambda: datetime.now(timezone.utc) + timedelta(seconds=10))
    QueueAgentRunHandler(
        runs=SqlAlchemyAgentRunRepository(session), queue=SqlAlchemyAgentTaskQueue(session),
        prompt_version="johnny-coaching-v1",
    ).queue_run(
        user_id="incremental-athlete", workflow_name="daily_review", trigger_type="scheduled",
        idempotency_key="scheduled-2026-10-20", task_type="coaching.sync",
        payload={"publication_date": "2026-10-20", "timezone_name": "Asia/Taipei"},
    )
    session.commit()
    runtime.work_drain(session, max_tasks=12)
    session.commit()

    runs = session.scalars(select(AgentRunModel)).all()
    assert len(runs) == 4
    assert all(run.status == "completed" for run in runs)
    assert len(session.scalars(select(SyncRunModel)).all()) == 1
    assert sum(resource == "activities" for resource, _, _ in feed.requests) == 1
    corrections = [run.id for run in runs if run.trigger_type == "evidence_change"]
    tasks = session.scalars(select(AgentTaskModel)).all()
    correction_tasks = [task for task in tasks if task.payload["run_id"] in corrections]
    assert len(correction_tasks) == 3
    sync_id = session.scalars(select(SyncRunModel)).one().id
    assert all(task.task_type == "agent.workflow"
               and task.payload["input"]["source_sync_run_id"] == sync_id for task in correction_tasks)
    for day in (17, 18, 19, 20):
        slot = store.get_review_slot("incremental-athlete", date(2026, 10, day))
        assert slot["freshness"] == "current"
        assert slot["current"]["publication_date"] == f"2026-10-{day}"


@pytest.mark.parametrize("cursor", [
    {"end_date": "not-a-date"}, {"end_date": "2026-10-22"},
    {"end_date": "2026-10-19", "timezone_name": "America/Los_Angeles"},
])
def test_unusable_checkpoint_restarts_initial_window(sync_context, cursor):
    session, integrations, connection, feed, sync = sync_context
    integrations.upsert_resource_cursor(connection.id, "activities", cursor)
    sync("2026-10-20")
    assert feed.requests[0] == ("activities", date(2026, 9, 21), date(2026, 10, 20))
    saved = session.scalar(select(IntegrationResourceCursorModel).where(
        IntegrationResourceCursorModel.integration_connection_id == connection.id,
        IntegrationResourceCursorModel.resource_type == "activities",
    ))
    assert saved.cursor_value["timezone_name"] == "Asia/Taipei"
