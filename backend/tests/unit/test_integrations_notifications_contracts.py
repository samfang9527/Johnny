from datetime import datetime, timezone

import pytest

from src.application.interfaces.integrations_notifications import (
    IntegrationStore,
    NotificationChannelGateway,
    NotificationStore,
    OutboxStore,
    ProviderAdapter,
    ProviderActivityStore,
)
from src.application.interfaces.persistence_repositories import IntegrationStore as ExportedIntegrationStore
from src.domain.integrations_notifications import (
    DomainValidationError,
    IntegrationConnectionRef,
    LineDeliveryResult,
    NormalizedProviderRecord,
    NotificationDelivery,
    NotificationIntent,
    OutboxEvent,
    ProviderFetchResult,
    SyncRun,
    SyncSummary,
)


def test_connection_ref_preserves_secret_reference_without_raw_credentials() -> None:
    connection = IntegrationConnectionRef.create(
        id="conn-1",
        user_id="user-1",
        provider="garmin_connect",
        credential_secret_ref="file:///Users/example/.johnny/garmin_tokens.json",
        credential_format="garminconnect-token-file",
        capabilities={"activities": True},
    )

    assert connection.credential_secret_ref == "file:///Users/example/.johnny/garmin_tokens.json"
    assert connection.to_safe_summary() == {
        "id": "conn-1",
        "user_id": "user-1",
        "provider": "garmin_connect",
        "provider_account_id": None,
        "credential_format": "garminconnect-token-file",
        "credential_status": "active",
        "status": "active",
        "capabilities": {"activities": True},
    }


def test_connection_ref_rejects_raw_credential_payloads() -> None:
    with pytest.raises(DomainValidationError):
        IntegrationConnectionRef.create(
            id="conn-1",
            user_id="user-1",
            provider="garmin_connect",
            credential_secret_ref='{"email":"runner@example.com","password":"secret"}',
        )


def test_sync_summary_counts_and_safe_error_summary() -> None:
    summary = SyncSummary.empty().record_fetched("activities", 3).record_stored("activities").record_duplicate("activities")
    failed = summary.record_failed("activities", "token=abc123 could not decode payload")

    assert failed.to_payload() == {
        "resources": {
            "activities": {
                "fetched": 3,
                "stored": 1,
                "duplicates": 1,
                "failed": 1,
                "errors": ["credential or token details redacted"],
            }
        }
    }


def test_sync_run_lifecycle_records_safe_summary() -> None:
    started_at = datetime(2027, 1, 1, 8, tzinfo=timezone.utc)
    finished_at = datetime(2027, 1, 1, 8, 1, tzinfo=timezone.utc)
    run = SyncRun.start(id="sync-1", integration_connection_id="conn-1", started_at=started_at)

    completed = run.complete(SyncSummary.empty().record_stored("activities"), finished_at=finished_at)
    failed = run.fail("password expired while fetching activities", finished_at=finished_at)

    assert completed.status == "succeeded"
    assert completed.summary.to_payload()["resources"]["activities"]["stored"] == 1
    assert failed.status == "failed"
    assert failed.summary.to_payload()["resources"]["sync"]["errors"] == ["credential or token details redacted"]


def test_provider_fetch_and_normalized_record_validate_payload_shape() -> None:
    payload = ProviderFetchResult.create(
        activities=[{"activityId": 123}],
        health=[{"calendarDate": "2027-01-01"}],
        cursor={"until": "2027-01-01"},
    )
    normalized = NormalizedProviderRecord.activity(source_payload_id="123", record={"id": "activity-1"})

    assert payload.activities == ({"activityId": 123},)
    assert payload.health == ({"calendarDate": "2027-01-01"},)
    assert normalized.resource_type == "activity"


def test_outbox_and_notification_contracts_capture_delivery_state() -> None:
    event = OutboxEvent.activity_ingested(
        user_id="user-1",
        activity_id="activity-1",
        provider_connection_id="conn-1",
        source_activity_id="garmin-1",
    )
    intent = NotificationIntent.recommendation(
        id="intent-1",
        user_id="user-1",
        recommendation_id="rec-1",
        channel="line",
        scheduled_for=datetime(2027, 1, 1, 9, tzinfo=timezone.utc),
        payload={"message": "Review recommendation", "approval_url": "https://johnny.example/recommendations/rec-1"},
    )
    delivery = NotificationDelivery.from_gateway_result(
        notification_intent_id="intent-1",
        result=LineDeliveryResult.failure(status_code=500, response={"error": "temporary"}),
    )

    assert event.topic == "ActivityIngested"
    assert intent.status == "pending"
    assert delivery.status == "failed"
    assert delivery.response["retryable"] is True


def test_application_interfaces_export_integration_roles() -> None:
    assert ExportedIntegrationStore is IntegrationStore
    assert "fetch" in ProviderAdapter.__dict__
    assert "get_activity_by_provider_identifier" in ProviderActivityStore.__dict__
    assert "create_event" in OutboxStore.__dict__
    assert "create_intent" in NotificationStore.__dict__
    assert "deliver" in NotificationChannelGateway.__dict__
