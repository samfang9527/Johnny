from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol

from src.application.interfaces.integrations_notifications import (
    IntegrationStore,
    OutboxStore,
    ProviderActivityStore,
    ProviderAdapter,
)
from src.domain.activity_health import CompletedActivity, DailyHealthMetrics
from src.domain.integrations_notifications import IntegrationConnectionRef, OutboxEvent, SyncSummary


class ProviderAccountAlreadyConnectedError(ValueError):
    pass


class SyncConnectionLifecycleStore(Protocol):
    def get_connection_by_provider_account(self, provider: str, provider_account_id: str) -> IntegrationConnectionRef | None: ...

    def replace_active_connections_for_user(self, user_id: str, *, except_connection_id: str | None = None) -> None: ...

    def create_connection(
        self,
        *,
        user_id: str,
        provider: str,
        provider_account_id: str | None = None,
        credential_secret_ref: str | None = None,
    ) -> IntegrationConnectionRef: ...

    def reactivate_connection(
        self,
        connection_id: str,
        *,
        credential_secret_ref: str | None = None,
    ) -> IntegrationConnectionRef: ...

    def reset_resource_cursors(self, integration_connection_id: str) -> None: ...


@dataclass(frozen=True)
class ProviderSyncCommand:
    user_id: str
    connection_id: str


@dataclass(frozen=True)
class ConnectSyncProviderCommand:
    user_id: str
    provider: str
    provider_account_id: str
    credential_secret_ref: str | None = None


class ConnectSyncProviderHandler:
    def __init__(self, *, integrations: SyncConnectionLifecycleStore) -> None:
        self._integrations = integrations

    def handle(self, command: ConnectSyncProviderCommand) -> IntegrationConnectionRef:
        existing = self._integrations.get_connection_by_provider_account(command.provider, command.provider_account_id)
        if existing is not None and existing.user_id != command.user_id:
            raise ProviderAccountAlreadyConnectedError("provider account already belongs to another user")

        if existing is not None:
            self._integrations.replace_active_connections_for_user(command.user_id, except_connection_id=existing.id)
            reactivated = self._integrations.reactivate_connection(
                existing.id,
                credential_secret_ref=command.credential_secret_ref,
            )
            self._integrations.reset_resource_cursors(reactivated.id)
            return reactivated

        self._integrations.replace_active_connections_for_user(command.user_id)
        return self._integrations.create_connection(
            user_id=command.user_id,
            provider=command.provider,
            provider_account_id=command.provider_account_id,
            credential_secret_ref=command.credential_secret_ref,
        )


class ProviderSyncHandler:
    def __init__(
        self,
        *,
        integrations: IntegrationStore,
        activities: ProviderActivityStore,
        outbox: OutboxStore,
        provider_adapter: ProviderAdapter,
        normalize_activity: Callable[[str, str, dict], CompletedActivity],
        normalize_health: Callable[[str, dict], DailyHealthMetrics],
    ) -> None:
        self._integrations = integrations
        self._activities = activities
        self._outbox = outbox
        self._provider_adapter = provider_adapter
        self._normalize_activity = normalize_activity
        self._normalize_health = normalize_health

    def handle(self, command: ProviderSyncCommand) -> SyncSummary:
        connection = self._integrations.get_connection_for_user(command.user_id, command.connection_id)
        if connection is None:
            raise ValueError("integration connection not found")

        sync_run = self._integrations.start_sync_run(connection.id)
        cursor = self._integrations.get_resource_cursor(connection.id, "sync")
        try:
            fetch_result = self._provider_adapter.fetch(connection, cursor=cursor)
        except Exception as exc:  # noqa: BLE001
            failed = self._integrations.fail_sync_run(sync_run.id, str(exc))
            return failed.summary

        summary = SyncSummary.empty()
        summary = summary.record_fetched("activities", len(fetch_result.activities))
        summary = summary.record_fetched("health", len(fetch_result.health))

        for payload in fetch_result.activities:
            try:
                activity = self._normalize_activity(command.user_id, connection.id, payload)
                existing = self._activities.get_activity_by_provider_identifier(
                    command.user_id,
                    connection.id,
                    activity.source_activity_id or "",
                )
                if existing is not None:
                    summary = summary.record_duplicate("activities")
                    continue
                saved = self._activities.save_activity(command.user_id, activity)
                if saved is None:
                    summary = summary.record_duplicate("activities")
                    continue
                summary = summary.record_stored("activities")
                self._outbox.create_event(
                    OutboxEvent.activity_ingested(
                        user_id=command.user_id,
                        activity_id=saved.id or "",
                        provider_connection_id=connection.id,
                        source_activity_id=activity.source_activity_id or "",
                    )
                )
            except Exception as exc:  # noqa: BLE001
                summary = summary.record_failed("activities", str(exc))

        for payload in fetch_result.health:
            try:
                metrics = self._normalize_health(command.user_id, payload)
                self._activities.save_daily_health_metrics(command.user_id, metrics)
                summary = summary.record_stored("health")
            except Exception as exc:  # noqa: BLE001
                summary = summary.record_failed("health", str(exc))

        if fetch_result.cursor:
            self._integrations.upsert_resource_cursor(connection.id, "sync", fetch_result.cursor)
        self._integrations.complete_sync_run(sync_run.id, summary)
        return summary
