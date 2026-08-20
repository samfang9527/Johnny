from dataclasses import replace
from datetime import date, datetime, timezone

from src.application.integrations import ProviderSyncCommand, ProviderSyncHandler
from src.domain.activity_health import CompletedActivity, DailyHealthMetrics
from src.domain.integrations_notifications import IntegrationConnectionRef, ProviderFetchResult, SyncRun, SyncSummary


class FakeProviderAdapter:
    def __init__(self, result: ProviderFetchResult | None = None, error: Exception | None = None) -> None:
        self.result = result
        self.error = error
        self.cursors: list[dict | None] = []

    def fetch(self, connection: IntegrationConnectionRef, cursor: dict | None = None) -> ProviderFetchResult:
        self.cursors.append(cursor)
        if self.error is not None:
            raise self.error
        return self.result or ProviderFetchResult.create()


class FakeIntegrationStore:
    def __init__(self) -> None:
        self.connection = IntegrationConnectionRef.create(id="conn-1", user_id="user-1", provider="garmin_connect")
        self.sync_run = SyncRun.start(
            id="sync-1",
            integration_connection_id="conn-1",
            started_at=datetime(2027, 1, 1, tzinfo=timezone.utc),
        )
        self.completed_summary: SyncSummary | None = None
        self.failed_run: SyncRun | None = None
        self.cursor = {"after": "old"}
        self.advanced_cursor: dict | None = None

    def get_connection_for_user(self, user_id: str, connection_id: str) -> IntegrationConnectionRef | None:
        if user_id == self.connection.user_id and connection_id == self.connection.id:
            return self.connection
        return None

    def start_sync_run(self, integration_connection_id: str) -> SyncRun:
        return self.sync_run

    def complete_sync_run(self, sync_run_id: str, summary: SyncSummary) -> SyncRun:
        self.completed_summary = summary
        return self.sync_run.complete(summary, finished_at=datetime(2027, 1, 1, 0, 1, tzinfo=timezone.utc))

    def fail_sync_run(self, sync_run_id: str, error: str) -> SyncRun:
        self.failed_run = self.sync_run.fail(error, finished_at=datetime(2027, 1, 1, 0, 1, tzinfo=timezone.utc))
        return self.failed_run

    def get_resource_cursor(self, integration_connection_id: str, resource_type: str) -> dict | None:
        return self.cursor if resource_type == "sync" else None

    def upsert_resource_cursor(self, integration_connection_id: str, resource_type: str, cursor_value: dict) -> dict:
        self.advanced_cursor = dict(cursor_value)
        return self.advanced_cursor


class FakeActivityStore:
    def __init__(self) -> None:
        self.activities: dict[tuple[str, str], CompletedActivity] = {}
        self.health: list[DailyHealthMetrics] = []

    def get_activity_by_provider_identifier(
        self,
        user_id: str,
        provider_connection_id: str,
        source_activity_id: str,
    ) -> CompletedActivity | None:
        return self.activities.get((provider_connection_id, source_activity_id))

    def save_activity(self, user_id: str, activity: CompletedActivity) -> CompletedActivity | None:
        saved = replace(activity, id=f"activity-{len(self.activities) + 1}")
        self.activities[(activity.provider_connection_id, activity.source_activity_id)] = saved
        return saved

    def save_daily_health_metrics(self, user_id: str, metrics: DailyHealthMetrics) -> DailyHealthMetrics:
        self.health.append(metrics)
        return metrics


class FakeOutboxStore:
    def __init__(self) -> None:
        self.events = []

    def create_event(self, event):
        self.events.append(event)
        return replace(event, id=f"event-{len(self.events)}")


def test_provider_sync_fetches_normalizes_persists_and_advances_cursor() -> None:
    integration_store = FakeIntegrationStore()
    activity_store = FakeActivityStore()
    outbox = FakeOutboxStore()
    adapter = FakeProviderAdapter(
        ProviderFetchResult.create(
            activities=[{"id": "garmin-1"}],
            health=[{"date": "2027-01-01"}],
            cursor={"after": "new"},
        )
    )
    handler = ProviderSyncHandler(
        integrations=integration_store,
        activities=activity_store,
        outbox=outbox,
        provider_adapter=adapter,
        normalize_activity=_normalize_activity,
        normalize_health=_normalize_health,
    )

    summary = handler.handle(ProviderSyncCommand(user_id="user-1", connection_id="conn-1"))

    assert adapter.cursors == [{"after": "old"}]
    assert summary.to_payload()["resources"]["activities"] == {
        "fetched": 1,
        "stored": 1,
        "duplicates": 0,
        "failed": 0,
        "errors": [],
    }
    assert summary.to_payload()["resources"]["health"]["stored"] == 1
    assert integration_store.advanced_cursor == {"after": "new"}
    assert len(outbox.events) == 1
    assert outbox.events[0].topic == "ActivityIngested"


def test_provider_sync_detects_duplicate_provider_activity_without_outbox_event() -> None:
    integration_store = FakeIntegrationStore()
    activity_store = FakeActivityStore()
    duplicate = _activity("garmin-1")
    activity_store.activities[(duplicate.provider_connection_id, duplicate.source_activity_id)] = duplicate
    outbox = FakeOutboxStore()
    handler = ProviderSyncHandler(
        integrations=integration_store,
        activities=activity_store,
        outbox=outbox,
        provider_adapter=FakeProviderAdapter(ProviderFetchResult.create(activities=[{"id": "garmin-1"}], cursor={"after": "same"})),
        normalize_activity=_normalize_activity,
        normalize_health=_normalize_health,
    )

    summary = handler.handle(ProviderSyncCommand(user_id="user-1", connection_id="conn-1"))

    assert summary.to_payload()["resources"]["activities"]["duplicates"] == 1
    assert summary.to_payload()["resources"]["activities"]["stored"] == 0
    assert outbox.events == []
    assert integration_store.advanced_cursor == {"after": "same"}


def test_provider_sync_records_partial_normalization_failures_and_still_advances_cursor() -> None:
    integration_store = FakeIntegrationStore()
    handler = ProviderSyncHandler(
        integrations=integration_store,
        activities=FakeActivityStore(),
        outbox=FakeOutboxStore(),
        provider_adapter=FakeProviderAdapter(
            ProviderFetchResult.create(activities=[{"id": "garmin-1"}, {"bad": True}], cursor={"after": "partial"})
        ),
        normalize_activity=lambda user_id, provider_connection_id, payload: (_normalize_activity(user_id, provider_connection_id, payload)),
        normalize_health=_normalize_health,
    )

    summary = handler.handle(ProviderSyncCommand(user_id="user-1", connection_id="conn-1"))

    assert summary.to_payload()["resources"]["activities"]["stored"] == 1
    assert summary.to_payload()["resources"]["activities"]["failed"] == 1
    assert integration_store.advanced_cursor == {"after": "partial"}


def test_provider_sync_failure_marks_run_failed_and_does_not_advance_cursor() -> None:
    integration_store = FakeIntegrationStore()
    handler = ProviderSyncHandler(
        integrations=integration_store,
        activities=FakeActivityStore(),
        outbox=FakeOutboxStore(),
        provider_adapter=FakeProviderAdapter(error=RuntimeError("token=abc123 expired")),
        normalize_activity=_normalize_activity,
        normalize_health=_normalize_health,
    )

    summary = handler.handle(ProviderSyncCommand(user_id="user-1", connection_id="conn-1"))

    assert integration_store.failed_run is not None
    assert integration_store.failed_run.status == "failed"
    assert summary.to_payload()["resources"]["sync"]["errors"] == ["credential or token details redacted"]
    assert integration_store.advanced_cursor is None


def _normalize_activity(user_id: str, provider_connection_id: str, payload: dict) -> CompletedActivity:
    return _activity(str(payload["id"]), user_id=user_id, provider_connection_id=provider_connection_id)


def _normalize_health(user_id: str, payload: dict) -> DailyHealthMetrics:
    return DailyHealthMetrics.create(
        user_id=user_id,
        source="garmin_connect",
        metric_date=date.fromisoformat(payload["date"]),
        resting_heart_rate=48,
    )


def _activity(
    source_activity_id: str,
    *,
    user_id: str = "user-1",
    provider_connection_id: str = "conn-1",
) -> CompletedActivity:
    return CompletedActivity.create(
        user_id=user_id,
        source="garmin_connect",
        source_activity_id=source_activity_id,
        provider_connection_id=provider_connection_id,
        started_at=datetime(2027, 1, 1, 7, tzinfo=timezone.utc),
        sport_type="running",
        distance_meters=5000,
        duration_seconds=1500,
    )
