from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from src.api.dependencies import CurrentUserDependency, SessionDependency, ensure_current_user
from src.api.errors import ApiNotFoundError
from src.api.schemas.common import DataEnvelope
from src.api.schemas.integrations import (
    IntegrationConnectionRequest,
    IntegrationConnectionResponse,
    ProviderWebhookRequest,
    SyncSummaryResponse,
)
from src.application.integrations import ProviderSyncCommand, ProviderSyncHandler
from src.domain.integrations_notifications import IntegrationConnectionRef, ProviderFetchResult
from src.infrastructure.database.activity_repository import SqlAlchemyActivityRepository
from src.infrastructure.database.integration_repository import SqlAlchemyIntegrationRepository
from src.infrastructure.database.outbox_repository import SqlAlchemyOutboxRepository
from src.infrastructure.integrations.garmin_normalizer import normalize_garmin_activity, normalize_garmin_daily_health


router = APIRouter(prefix="/api/integrations", tags=["integrations"])


@router.post("/connections", response_model=DataEnvelope[IntegrationConnectionResponse])
def create_connection(
    payload: IntegrationConnectionRequest,
    current_user: CurrentUserDependency,
    session: SessionDependency,
) -> DataEnvelope[IntegrationConnectionResponse]:
    ensure_current_user(session, current_user)
    connection = SqlAlchemyIntegrationRepository(session).create_connection(
        user_id=current_user.id,
        provider=payload.provider,
        provider_account_id=payload.provider_account_id,
        credential_secret_ref=payload.credential_secret_ref,
    )
    return DataEnvelope(data=_connection_response(connection))


@router.post("/webhooks/{provider}/{connection_id}")
def receive_webhook(
    provider: str,
    connection_id: str,
    payload: ProviderWebhookRequest,
    current_user: CurrentUserDependency,
    session: SessionDependency,
) -> DataEnvelope[SyncSummaryResponse]:
    repository = SqlAlchemyIntegrationRepository(session)
    connection = repository.get_connection_for_user(current_user.id, connection_id)
    if connection is None or connection.provider != provider:
        raise ApiNotFoundError("integration connection not found")
    handler = ProviderSyncHandler(
        integrations=repository,
        activities=SqlAlchemyActivityRepository(session),
        outbox=SqlAlchemyOutboxRepository(session),
        provider_adapter=_WebhookProviderAdapter(payload),
        normalize_activity=lambda user_id, provider_connection_id, activity_payload: normalize_garmin_activity(
            user_id=user_id,
            provider_connection_id=provider_connection_id,
            payload=activity_payload,
        ),
        normalize_health=lambda user_id, health_payload: normalize_garmin_daily_health(
            user_id=user_id,
            payload=health_payload,
        ),
    )
    summary = handler.handle(ProviderSyncCommand(user_id=current_user.id, connection_id=connection_id))
    return DataEnvelope(data=SyncSummaryResponse(**summary.to_payload()))


class _WebhookProviderAdapter:
    def __init__(self, payload: ProviderWebhookRequest) -> None:
        self._payload = payload

    def fetch(self, connection: IntegrationConnectionRef, cursor: dict[str, Any] | None = None) -> ProviderFetchResult:
        return ProviderFetchResult.create(
            activities=self._payload.activities,
            health=self._payload.health,
            cursor=self._payload.cursor,
        )


def _connection_response(connection: IntegrationConnectionRef) -> IntegrationConnectionResponse:
    return IntegrationConnectionResponse(
        id=connection.id,
        user_id=connection.user_id,
        provider=connection.provider,
        credential_secret_ref=connection.credential_secret_ref,
    )
