from datetime import date, datetime, timezone

from src.application.daily_advice_sync import activity_sync_usable, queue_after_completed_sync, recovery_data_limited
from src.domain.integrations_notifications import IntegrationConnectionRef, SyncRun, SyncSummary


def test_activity_sync_requires_attempted_success_even_when_zero_items_were_fetched() -> None:
    assert activity_sync_usable(SyncSummary.empty(), "succeeded", "active") is False
    empty_success = SyncSummary.empty().record_fetched("activities", 0)
    assert activity_sync_usable(empty_success, "succeeded", "active") is True
    assert activity_sync_usable(empty_success, "started", "active") is False
    assert activity_sync_usable(empty_success, "succeeded", "requires_reauth") is False
    failed = empty_success.record_failed("activities", "Garmin activity import failed")
    assert activity_sync_usable(failed, "failed", "active") is False


def test_health_failure_after_successful_activities_allows_limited_recovery_advice() -> None:
    summary = SyncSummary.empty().record_fetched("activities", 0).record_failed(
        "sleep", "Garmin resource sync failed"
    )
    assert activity_sync_usable(summary, "failed", "active") is True
    assert recovery_data_limited(summary) is True
    assert recovery_data_limited(SyncSummary.empty().record_fetched("activities", 0)) is False


def test_completed_sync_without_owning_plan_does_not_queue_advice() -> None:
    class NoPlanStore:
        def get_current_plan_for_user(self, user_id):
            return None

    class MustNotQueue:
        def queue_run(self, **kwargs):
            raise AssertionError("no advice run should be queued")

    result = queue_after_completed_sync(
        user_id="athlete", anchor_date=date(2027, 1, 28),
        sync_run=SyncRun(
            id="sync-1", integration_connection_id="connection-1", status="succeeded",
            started_at=datetime(2027, 1, 28, tzinfo=timezone.utc),
            finished_at=datetime(2027, 1, 28, tzinfo=timezone.utc),
            summary=SyncSummary.empty().record_fetched("activities", 0),
        ),
        connection=IntegrationConnectionRef.create(
            id="connection-1", user_id="athlete", provider="garmin_connect",
        ),
        training_plans=NoPlanStore(), advice=None, queue_runs=MustNotQueue(),
    )

    assert result is None
