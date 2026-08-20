from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from src.application.interfaces.integrations_notifications import (
    IntegrationStore,
    OutboxStore,
    ProviderActivityStore,
    ProviderAdapter,
)
from src.domain.activity_health import CompletedActivity, DailyHealthMetrics
from src.domain.integrations_notifications import OutboxEvent, SyncSummary


@dataclass(frozen=True)
class ProviderSyncCommand:
    user_id: str
    connection_id: str


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
