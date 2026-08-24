from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.domain.integrations_notifications import IntegrationConnectionRef, IntegrationCredential, SyncRun, SyncSummary

from .models import IntegrationConnectionModel, IntegrationCredentialModel, IntegrationResourceCursorModel, SyncRunModel, utc_now


class SqlAlchemyIntegrationRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create_connection(
        self,
        *,
        user_id: str,
        provider: str,
        provider_account_id: str | None = None,
        provider_display_name: str | None = None,
        auth_scheme: str = "oauth2",
        credential_secret_ref: str | None = None,
        credential_format: str | None = None,
        capabilities: dict | None = None,
        provider_metadata: dict | None = None,
    ) -> IntegrationConnectionRef:
        connection = IntegrationConnectionModel(
            user_id=user_id,
            provider=provider,
            provider_account_id=provider_account_id,
            provider_display_name=provider_display_name,
            auth_scheme=auth_scheme,
            credential_secret_ref=credential_secret_ref,
            credential_format=credential_format,
            capabilities=capabilities or {},
            provider_metadata=provider_metadata or {},
        )
        self._session.add(connection)
        self._session.flush()
        return _connection_from_model(connection)

    def get_connection_for_user(self, user_id: str, connection_id: str) -> IntegrationConnectionRef | None:
        connection = self._session.scalar(
            select(IntegrationConnectionModel).where(
                IntegrationConnectionModel.id == connection_id,
                IntegrationConnectionModel.user_id == user_id,
            )
        )
        if connection is None:
            return None
        return _connection_from_model(connection)

    def get_connection_by_provider_account(self, provider: str, provider_account_id: str) -> IntegrationConnectionRef | None:
        connection = self._session.scalar(
            select(IntegrationConnectionModel).where(
                IntegrationConnectionModel.provider == provider,
                IntegrationConnectionModel.provider_account_id == provider_account_id,
            )
        )
        if connection is None:
            return None
        return _connection_from_model(connection)

    def list_active_connections_for_user(self, user_id: str) -> list[IntegrationConnectionRef]:
        connections = self._session.scalars(
            select(IntegrationConnectionModel).where(
                IntegrationConnectionModel.user_id == user_id,
                IntegrationConnectionModel.status == "active",
            )
        )
        return [_connection_from_model(connection) for connection in connections]

    def replace_active_connections_for_user(self, user_id: str, *, except_connection_id: str | None = None) -> None:
        now = utc_now()
        connections = self._session.scalars(
            select(IntegrationConnectionModel).where(
                IntegrationConnectionModel.user_id == user_id,
                IntegrationConnectionModel.status == "active",
            )
        )
        for connection in connections:
            if connection.id == except_connection_id:
                continue
            connection.status = "replaced"
            connection.disconnected_at = now
            connection.sync_status = "idle"
        self._session.flush()

    def reactivate_connection(
        self,
        connection_id: str,
        *,
        credential_secret_ref: str | None = None,
        credential_format: str | None = None,
        capabilities: dict[str, Any] | None = None,
        provider_metadata: dict[str, Any] | None = None,
        provider_display_name: str | None = None,
        auth_scheme: str | None = None,
    ) -> IntegrationConnectionRef:
        connection = self._require_connection(connection_id)
        connection.status = "active"
        connection.credential_status = "active"
        connection.sync_status = "idle"
        connection.credential_secret_ref = credential_secret_ref
        connection.credential_format = credential_format
        if provider_display_name is not None:
            connection.provider_display_name = provider_display_name
        if auth_scheme is not None:
            connection.auth_scheme = auth_scheme
        if capabilities is not None:
            connection.capabilities = capabilities
        if provider_metadata is not None:
            connection.provider_metadata = provider_metadata
        connection.connected_at = utc_now()
        connection.disconnected_at = None
        connection.last_sync_error = None
        self._session.flush()
        return _connection_from_model(connection)

    def reset_resource_cursors(self, integration_connection_id: str) -> None:
        cursors = self._session.scalars(
            select(IntegrationResourceCursorModel).where(
                IntegrationResourceCursorModel.integration_connection_id == integration_connection_id,
            )
        )
        for cursor in cursors:
            cursor.cursor_value = {}
            cursor.sync_from = None
            cursor.sync_until = None
            cursor.last_successful_sync_at = None
            cursor.status = "stale"
        self._session.flush()

    def upsert_credential(self, credential: IntegrationCredential) -> IntegrationCredential:
        existing = self._session.scalar(
            select(IntegrationCredentialModel).where(
                IntegrationCredentialModel.integration_connection_id == credential.connection_id,
            )
        )
        if existing is None:
            existing = IntegrationCredentialModel(integration_connection_id=credential.connection_id)
            self._session.add(existing)
        existing.credential_format = credential.credential_format
        existing.encrypted_payload = credential.encrypted_payload
        existing.key_id = credential.key_id
        existing.lifecycle_metadata = dict(credential.lifecycle_metadata or {})
        self._session.flush()
        return _credential_from_model(existing)

    def get_credential_for_connection(self, integration_connection_id: str) -> IntegrationCredential | None:
        credential = self._session.scalar(
            select(IntegrationCredentialModel).where(
                IntegrationCredentialModel.integration_connection_id == integration_connection_id,
            )
        )
        if credential is None:
            return None
        return _credential_from_model(credential)

    def delete_credential_for_connection(self, integration_connection_id: str) -> None:
        credential = self._session.scalar(
            select(IntegrationCredentialModel).where(
                IntegrationCredentialModel.integration_connection_id == integration_connection_id,
            )
        )
        if credential is not None:
            self._session.delete(credential)
            self._session.flush()

    def start_sync_run(self, integration_connection_id: str) -> SyncRun:
        now = utc_now()
        connection = self._session.get(IntegrationConnectionModel, integration_connection_id)
        if connection is None:
            raise ValueError(f"Integration connection not found: {integration_connection_id}")
        connection.sync_status = "running"
        connection.last_sync_started_at = now
        connection.last_sync_error = None
        model = SyncRunModel(
            integration_connection_id=integration_connection_id,
            status="started",
            started_at=now,
            summary=SyncSummary.empty().to_payload(),
        )
        self._session.add(model)
        self._session.flush()
        return _sync_run_from_model(model)

    def complete_sync_run(self, sync_run_id: str, summary: SyncSummary) -> SyncRun:
        run = self._require_sync_run(sync_run_id)
        now = utc_now()
        run.status = "succeeded"
        run.finished_at = now
        run.summary = summary.to_payload()
        connection = self._session.get(IntegrationConnectionModel, run.integration_connection_id)
        if connection is not None:
            connection.sync_status = "idle"
            connection.last_sync_completed_at = now
            connection.last_sync_error = None
        self._session.flush()
        return _sync_run_from_model(run)

    def fail_sync_run(self, sync_run_id: str, error: str) -> SyncRun:
        run = self._require_sync_run(sync_run_id)
        now = utc_now()
        failed = _sync_run_from_model(run).fail(error, finished_at=now)
        run.status = failed.status
        run.finished_at = failed.finished_at
        run.summary = failed.summary.to_payload()
        connection = self._session.get(IntegrationConnectionModel, run.integration_connection_id)
        if connection is not None:
            connection.sync_status = "failed"
            connection.last_sync_error = failed.summary.to_payload()["resources"]["sync"]["errors"][0]
        self._session.flush()
        return _sync_run_from_model(run)

    def get_resource_cursor(self, integration_connection_id: str, resource_type: str) -> dict | None:
        cursor = self._session.scalar(
            select(IntegrationResourceCursorModel).where(
                IntegrationResourceCursorModel.integration_connection_id == integration_connection_id,
                IntegrationResourceCursorModel.resource_type == resource_type,
            )
        )
        if cursor is None:
            return None
        return dict(cursor.cursor_value or {})

    def upsert_resource_cursor(
        self,
        integration_connection_id: str,
        resource_type: str,
        cursor_value: dict,
        *,
        sync_from=None,  # noqa: ANN001
        sync_until=None,  # noqa: ANN001
    ) -> dict:
        cursor = self._session.scalar(
            select(IntegrationResourceCursorModel).where(
                IntegrationResourceCursorModel.integration_connection_id == integration_connection_id,
                IntegrationResourceCursorModel.resource_type == resource_type,
            )
        )
        if cursor is None:
            cursor = IntegrationResourceCursorModel(
                integration_connection_id=integration_connection_id,
                resource_type=resource_type,
            )
            self._session.add(cursor)
        cursor.cursor_value = dict(cursor_value)
        cursor.sync_from = sync_from
        cursor.sync_until = sync_until
        cursor.status = "ready"
        cursor.last_successful_sync_at = utc_now()
        self._session.flush()
        return dict(cursor.cursor_value)

    def _require_sync_run(self, sync_run_id: str) -> SyncRunModel:
        run = self._session.get(SyncRunModel, sync_run_id)
        if run is None:
            raise ValueError(f"Sync run not found: {sync_run_id}")
        return run

    def _require_connection(self, connection_id: str) -> IntegrationConnectionModel:
        connection = self._session.get(IntegrationConnectionModel, connection_id)
        if connection is None:
            raise ValueError(f"Integration connection not found: {connection_id}")
        return connection


def _connection_from_model(model: IntegrationConnectionModel) -> IntegrationConnectionRef:
    return IntegrationConnectionRef.create(
        id=model.id,
        user_id=model.user_id,
        provider=model.provider,
        provider_account_id=model.provider_account_id,
        provider_display_name=model.provider_display_name,
        auth_scheme=model.auth_scheme,
        credential_secret_ref=model.credential_secret_ref,
        credential_format=model.credential_format,
        credential_status=model.credential_status,
        status=model.status,
        capabilities=model.capabilities or {},
        provider_metadata=model.provider_metadata or {},
    )


def _credential_from_model(model: IntegrationCredentialModel) -> IntegrationCredential:
    return IntegrationCredential.create(
        id=model.id,
        connection_id=model.integration_connection_id,
        credential_format=model.credential_format,
        encrypted_payload=model.encrypted_payload,
        key_id=model.key_id,
        lifecycle_metadata=model.lifecycle_metadata or {},
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


def _sync_run_from_model(model: SyncRunModel) -> SyncRun:
    return SyncRun(
        id=model.id,
        integration_connection_id=model.integration_connection_id,
        status=model.status,
        started_at=model.started_at,
        finished_at=model.finished_at,
        summary=SyncSummary.from_payload(model.summary),
    )
