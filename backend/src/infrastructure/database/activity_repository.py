from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import ActivityModel, IntegrationConnectionModel, IntegrationResourceCursorModel, utc_now


class SqlAlchemyActivityRepository:
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
    ) -> IntegrationConnectionModel:
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
        return connection

    def record_credential_refresh(self, connection_id: str) -> IntegrationConnectionModel:
        connection = self._session.get(IntegrationConnectionModel, connection_id)
        if connection is None:
            raise ValueError(f"Integration connection not found: {connection_id}")
        refreshed_at = utc_now()
        connection.last_credential_refresh_at = refreshed_at
        connection.credential_rotated_at = refreshed_at
        self._session.flush()
        return connection

    def upsert_resource_cursor(
        self,
        *,
        integration_connection_id: str,
        resource_type: str,
        cursor_value: dict | None = None,
        sync_from: datetime | None = None,
        sync_until: datetime | None = None,
        status: str = "ready",
        metadata_json: dict | None = None,
    ) -> IntegrationResourceCursorModel:
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

        cursor.cursor_value = cursor_value or {}
        cursor.sync_from = sync_from
        cursor.sync_until = sync_until
        if status == "ready":
            cursor.last_successful_sync_at = utc_now()
        cursor.status = status
        cursor.metadata_json = metadata_json or {}
        self._session.flush()
        return cursor

    def list_for_user(self, user_id: str) -> list[ActivityModel]:
        return list(self._session.scalars(select(ActivityModel).where(ActivityModel.user_id == user_id)))
