from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol

from src.domain.activity_health import CompletedActivity, DailyHealthMetrics
from src.domain.integrations_notifications import (
    IntegrationConnectionRef,
    IntegrationCredential,
    LineDeliveryResult,
    NotificationDelivery,
    NotificationIntent,
    OutboxEvent,
    ProviderFetchResult,
    SyncRun,
    SyncSummary,
)


class ProviderAdapter(Protocol):
    def fetch(self, connection: IntegrationConnectionRef, cursor: dict[str, Any] | None = None) -> ProviderFetchResult:
        ...


class ProviderActivityStore(Protocol):
    def get_activity_by_provider_identifier(
        self,
        user_id: str,
        provider_connection_id: str,
        source_activity_id: str,
    ) -> CompletedActivity | None:
        ...

    def save_activity(self, user_id: str, activity: CompletedActivity) -> CompletedActivity | None:
        ...

    def save_daily_health_metrics(self, user_id: str, metrics: DailyHealthMetrics) -> DailyHealthMetrics:
        ...


class IntegrationStore(Protocol):
    def get_connection_for_user(self, user_id: str, connection_id: str) -> IntegrationConnectionRef | None:
        ...

    def start_sync_run(self, integration_connection_id: str) -> SyncRun:
        ...

    def complete_sync_run(self, sync_run_id: str, summary: SyncSummary, *, status: str = "succeeded") -> SyncRun:
        ...

    def fail_sync_run(self, sync_run_id: str, error: str) -> SyncRun:
        ...

    def mark_connection_requires_reauth(self, integration_connection_id: str, error: str) -> IntegrationConnectionRef:
        ...

    def get_resource_cursor(self, integration_connection_id: str, resource_type: str) -> dict[str, Any] | None:
        ...

    def upsert_resource_cursor(
        self,
        integration_connection_id: str,
        resource_type: str,
        cursor_value: dict[str, Any],
        *,
        sync_from: datetime | None = None,
        sync_until: datetime | None = None,
    ) -> dict[str, Any]:
        ...


class IntegrationCredentialStore(Protocol):
    def upsert_credential(self, credential: IntegrationCredential) -> IntegrationCredential:
        ...

    def get_credential_for_connection(self, integration_connection_id: str) -> IntegrationCredential | None:
        ...

    def delete_credential_for_connection(self, integration_connection_id: str) -> None:
        ...


class OutboxStore(Protocol):
    def create_event(self, event: OutboxEvent) -> OutboxEvent:
        ...

    def list_pending_events(self, *, limit: int | None = None, offset: int = 0) -> list[OutboxEvent]:
        ...


class NotificationStore(Protocol):
    def create_intent(self, intent: NotificationIntent) -> NotificationIntent:
        ...

    def get_intent_for_user(self, user_id: str, intent_id: str | None) -> NotificationIntent | None:
        ...

    def list_intents_for_user(
        self,
        user_id: str,
        *,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[NotificationIntent]:
        ...

    def record_delivery(self, delivery: NotificationDelivery) -> NotificationDelivery:
        ...

    def list_deliveries_for_intent(
        self,
        notification_intent_id: str,
        *,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[NotificationDelivery]:
        ...

    def mark_intent_delivered(self, intent_id: str) -> NotificationIntent:
        ...

    def mark_intent_retryable(self, intent_id: str) -> NotificationIntent:
        ...

    def mark_intent_failed(self, intent_id: str) -> NotificationIntent:
        ...


class NotificationChannelGateway(Protocol):
    def deliver(self, intent: NotificationIntent) -> LineDeliveryResult:
        ...
