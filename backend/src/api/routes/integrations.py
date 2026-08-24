from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from src.api.dependencies import CurrentUserDependency, SessionDependency, ensure_current_user
from src.api.errors import ApiConflictError, ApiNotFoundError, ApiUnauthorizedError, ApiUnavailableError
from src.api.schemas.common import DataEnvelope
from src.api.schemas.integrations import (
    GarminConnectRequest,
    IntegrationConnectionRequest,
    IntegrationConnectionResponse,
    ProviderWebhookRequest,
    SyncSummaryResponse,
)
from src.application.integrations import (
    ConnectGarminAccountCommand,
    ConnectGarminAccountHandler,
    ConnectSyncProviderCommand,
    ConnectSyncProviderHandler,
    GarminAuthenticationError,
    GarminIntegrationConfigurationError,
    GarminLoginAdapter,
    ProviderAccountAlreadyConnectedError,
    ProviderSyncCommand,
    ProviderSyncHandler,
)
from src.domain.integrations_notifications import IntegrationConnectionRef, ProviderFetchResult
from src.infrastructure.database.activity_repository import SqlAlchemyActivityRepository
from src.infrastructure.database.integration_repository import SqlAlchemyIntegrationRepository
from src.infrastructure.database.outbox_repository import SqlAlchemyOutboxRepository
from src.infrastructure.integrations.garmin_normalizer import normalize_garmin_activity, normalize_garmin_daily_health
from src.infrastructure.security.integration_credentials import CredentialCipher, load_garmin_credential_cipher


router = APIRouter(prefix="/integrations", tags=["integrations"])


class _UnavailableGarminLoginAdapter:
    def exchange_credentials(self, *, email: str, password: str, region: str):  # noqa: ANN201
        raise GarminIntegrationConfigurationError("Garmin Connect login adapter is not configured")


def get_garmin_login_adapter() -> GarminLoginAdapter:
    return _UnavailableGarminLoginAdapter()


def get_garmin_credential_cipher() -> CredentialCipher:
    return load_garmin_credential_cipher()


@router.post("/connections", response_model=DataEnvelope[IntegrationConnectionResponse])
def create_connection(
    payload: IntegrationConnectionRequest,
    current_user: CurrentUserDependency,
    session: SessionDependency,
) -> DataEnvelope[IntegrationConnectionResponse]:
    ensure_current_user(session, current_user)
    try:
        connection = ConnectSyncProviderHandler(integrations=SqlAlchemyIntegrationRepository(session)).handle(
            ConnectSyncProviderCommand(
                user_id=current_user.id,
                provider=payload.provider,
                provider_account_id=payload.provider_account_id,
                credential_secret_ref=payload.credential_secret_ref,
            )
        )
    except ProviderAccountAlreadyConnectedError as exc:
        raise ApiConflictError(str(exc)) from exc
    return DataEnvelope(data=_connection_response(connection))


@router.post("/garmin/connect", response_model=DataEnvelope[IntegrationConnectionResponse])
def connect_garmin(
    payload: GarminConnectRequest,
    current_user: CurrentUserDependency,
    session: SessionDependency,
    garmin: GarminLoginAdapter = Depends(get_garmin_login_adapter),
    cipher: CredentialCipher = Depends(get_garmin_credential_cipher),
) -> DataEnvelope[IntegrationConnectionResponse]:
    ensure_current_user(session, current_user)
    repository = SqlAlchemyIntegrationRepository(session)
    try:
        connection = ConnectGarminAccountHandler(
            integrations=repository,
            credentials=repository,
            garmin=garmin,
            cipher=cipher,
        ).handle(
            ConnectGarminAccountCommand(
                user_id=current_user.id,
                email=payload.email,
                password=payload.password,
                region=payload.region,
            )
        )
    except ProviderAccountAlreadyConnectedError as exc:
        raise ApiConflictError(str(exc)) from exc
    except GarminIntegrationConfigurationError as exc:
        raise ApiUnavailableError("Garmin integration is not configured") from exc
    except GarminAuthenticationError as exc:
        raise ApiUnauthorizedError("Garmin credentials could not be verified") from exc
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
    if connection is None or connection.provider != provider or connection.status != "active":
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
        provider_account_id=connection.provider_account_id or "",
        provider_display_name=connection.provider_display_name,
        status=connection.status,
        credential_secret_ref=connection.credential_secret_ref,
        credential_format=connection.credential_format,
        credential_status=connection.credential_status,
    )
