from __future__ import annotations

from datetime import datetime, timezone
import os
from secrets import compare_digest
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Header
from sqlalchemy.orm import Session

from src.api.dependencies import CurrentUserDependency, SessionDependency, ensure_current_user
from src.api.errors import ApiConflictError, ApiNotFoundError, ApiUnauthorizedError, ApiUnavailableError
from src.api.schemas.common import DataEnvelope
from src.api.schemas.integrations import (
    GarminAdminTokenImportRequest,
    GarminConnectRequest,
    IntegrationConnectionRequest,
    IntegrationConnectionResponse,
    ProviderWebhookRequest,
    SyncSummaryResponse,
)
from src.api.schemas.agent_runs import QueuedAgentRunResponse
from src.application.async_agent_runs import QueueAgentRunHandler
from src.application.daily_advice_sync import queue_after_completed_sync
from src.application.integrations import (
    AdminImportGarminTokenCommand,
    AdminImportGarminTokenHandler,
    ConnectGarminAccountCommand,
    ConnectGarminAccountHandler,
    ConnectSyncProviderCommand,
    ConnectSyncProviderHandler,
    DisconnectGarminConnectionCommand,
    DisconnectGarminConnectionHandler,
    GARMIN_PROVIDER,
    GarminInitialSyncCommand,
    GarminInitialSyncHandler,
    GarminAuthenticationError,
    GarminIntegrationConfigurationError,
    GarminLoginAdapter,
    GarminResourceAdapter,
    ProviderAccountAlreadyConnectedError,
    ProviderSyncCommand,
    ProviderSyncHandler,
)
from src.domain.integrations_notifications import IntegrationConnectionRef, ProviderFetchResult, SyncAlreadyRunningError, SyncSummary
from src.infrastructure.database.activity_repository import SqlAlchemyActivityRepository
from src.infrastructure.database.agent_run_repository import SqlAlchemyAgentRunRepository
from src.infrastructure.database.agent_task_queue import SqlAlchemyAgentTaskQueue
from src.infrastructure.database.athlete_race_repository import SqlAlchemyAthleteRaceRepository
from src.infrastructure.database.daily_advice_repository import SqlAlchemyDailyAdviceRepository
from src.infrastructure.database.integration_repository import SqlAlchemyIntegrationRepository
from src.infrastructure.database.outbox_repository import SqlAlchemyOutboxRepository
from src.infrastructure.database.training_plan_repository import SqlAlchemyTrainingPlanRepository
from src.infrastructure.integrations.garminconnect_adapter import GarminConnectLoginAdapter, GarminConnectResourceAdapter
from src.infrastructure.integrations.garmin_normalizer import normalize_garmin_activity, normalize_garmin_daily_health
from src.infrastructure.security.integration_credentials import CredentialCipher, load_garmin_credential_cipher
from src.infrastructure.llm.settings import resolve_queued_daily_advice_provider


router = APIRouter(prefix="/integrations", tags=["integrations"])


def get_garmin_login_adapter() -> GarminLoginAdapter:
    return GarminConnectLoginAdapter()


def get_garmin_credential_cipher() -> CredentialCipher:
    return load_garmin_credential_cipher()


def get_garmin_resource_adapter(
    session: SessionDependency,
    cipher: CredentialCipher = Depends(get_garmin_credential_cipher),
) -> GarminResourceAdapter:
    return GarminConnectResourceAdapter(
        credentials=SqlAlchemyIntegrationRepository(session),
        cipher=cipher,
    )


@router.get("/connections", response_model=DataEnvelope[list[IntegrationConnectionResponse]])
def list_connections(
    current_user: CurrentUserDependency,
    session: SessionDependency,
) -> DataEnvelope[list[IntegrationConnectionResponse]]:
    ensure_current_user(session, current_user)
    repository = SqlAlchemyIntegrationRepository(session)
    connections = repository.list_active_connections_for_user(current_user.id)
    return DataEnvelope(
        data=[
            _connection_response(
                connection,
                sync_summary=(
                    latest_sync.summary
                    if (latest_sync := repository.get_latest_sync_run_for_connection(connection.id))
                    else None
                ),
            )
            for connection in connections
        ]
    )


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
    resource_adapter: GarminResourceAdapter = Depends(get_garmin_resource_adapter),
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
        sync_summary = _run_garmin_sync(
            repository=repository,
            session=session,
            user_id=current_user.id,
            connection_id=connection.id,
            resource_adapter=resource_adapter,
        )
        connection = repository.get_connection_for_user(current_user.id, connection.id) or connection
        daily_advice_run = _queue_daily_advice_after_sync(
            session, repository=repository, user_id=current_user.id, connection=connection,
        )
    except ProviderAccountAlreadyConnectedError as exc:
        raise ApiConflictError(str(exc)) from exc
    except SyncAlreadyRunningError as exc:
        raise ApiConflictError("Garmin sync is already running") from exc
    except GarminIntegrationConfigurationError as exc:
        raise ApiUnavailableError("Garmin integration is not configured") from exc
    except GarminAuthenticationError as exc:
        raise ApiUnauthorizedError("Garmin credentials could not be verified") from exc
    return DataEnvelope(data=_connection_response(connection, sync_summary=sync_summary, daily_advice_run=daily_advice_run))


@router.delete("/connections/{connection_id}", response_model=DataEnvelope[IntegrationConnectionResponse])
def disconnect_connection(
    connection_id: str,
    current_user: CurrentUserDependency,
    session: SessionDependency,
) -> DataEnvelope[IntegrationConnectionResponse]:
    ensure_current_user(session, current_user)
    repository = SqlAlchemyIntegrationRepository(session)
    try:
        connection = DisconnectGarminConnectionHandler(integrations=repository).handle(
            DisconnectGarminConnectionCommand(user_id=current_user.id, connection_id=connection_id)
        )
    except ValueError as exc:
        raise ApiNotFoundError("integration connection not found") from exc
    return DataEnvelope(data=_connection_response(connection))


@router.post("/connections/{connection_id}/admin-token-import", response_model=DataEnvelope[IntegrationConnectionResponse])
def admin_import_garmin_token(
    connection_id: str,
    payload: GarminAdminTokenImportRequest,
    current_user: CurrentUserDependency,
    session: SessionDependency,
    admin_token: str | None = Header(default=None, alias="X-Johnny-Admin-Token"),
    cipher: CredentialCipher = Depends(get_garmin_credential_cipher),
    resource_adapter: GarminResourceAdapter = Depends(get_garmin_resource_adapter),
) -> DataEnvelope[IntegrationConnectionResponse]:
    ensure_current_user(session, current_user)
    _require_admin_token(admin_token)
    repository = SqlAlchemyIntegrationRepository(session)
    try:
        connection = AdminImportGarminTokenHandler(
            integrations=repository,
            credentials=repository,
            cipher=cipher,
        ).handle(
            AdminImportGarminTokenCommand(
                user_id=current_user.id,
                connection_id=connection_id,
                session_payload=payload.session_payload,
            )
        )
        sync_summary = _run_garmin_sync(
            repository=repository, session=session, user_id=current_user.id,
            connection_id=connection.id, resource_adapter=resource_adapter,
        )
        connection = repository.get_connection_for_user(current_user.id, connection.id) or connection
        daily_advice_run = _queue_daily_advice_after_sync(
            session, repository=repository, user_id=current_user.id, connection=connection,
        )
    except ValueError as exc:
        raise ApiNotFoundError("integration connection not found") from exc
    except SyncAlreadyRunningError as exc:
        raise ApiConflictError("Garmin sync is already running") from exc
    return DataEnvelope(data=_connection_response(connection, sync_summary=sync_summary, daily_advice_run=daily_advice_run))


@router.post("/connections/{connection_id}/sync", response_model=DataEnvelope[IntegrationConnectionResponse])
def sync_connection(
    connection_id: str,
    current_user: CurrentUserDependency,
    session: SessionDependency,
    resource_adapter: GarminResourceAdapter = Depends(get_garmin_resource_adapter),
) -> DataEnvelope[IntegrationConnectionResponse]:
    ensure_current_user(session, current_user)
    repository = SqlAlchemyIntegrationRepository(session)
    connection = repository.get_connection_for_user(current_user.id, connection_id)
    if connection is None or connection.provider != GARMIN_PROVIDER or connection.status != "active":
        raise ApiNotFoundError("integration connection not found")
    if connection.sync_status == "running":
        running = repository.get_running_sync_run_for_connection(connection.id)
        if running is None:
            raise ApiConflictError("Garmin sync is already running")
        return DataEnvelope(data=_connection_response(connection, sync_summary=running.summary))
    if connection.credential_status == "requires_reauth":
        sync_summary = _run_garmin_sync(
            repository=repository,
            session=session,
            user_id=current_user.id,
            connection_id=connection.id,
            resource_adapter=resource_adapter,
        )
        connection = repository.get_connection_for_user(current_user.id, connection.id) or connection
        daily_advice_run = _queue_daily_advice_after_sync(
            session, repository=repository, user_id=current_user.id, connection=connection,
        )
        return DataEnvelope(data=_connection_response(connection, sync_summary=sync_summary, daily_advice_run=daily_advice_run))
    try:
        sync_run = repository.start_sync_run(connection.id)
        session.commit()
        sync_summary = _run_garmin_sync(
            repository=repository,
            session=session,
            user_id=current_user.id,
            connection_id=connection.id,
            resource_adapter=resource_adapter,
            sync_run_id=sync_run.id,
        )
    except GarminIntegrationConfigurationError as exc:
        repository.fail_sync_run(sync_run.id, "Garmin integration is not configured")
        refreshed = repository.get_connection_for_user(current_user.id, connection.id)
        if refreshed is not None:
            _queue_daily_advice_after_sync(
                session, repository=repository, user_id=current_user.id, connection=refreshed,
            )
        session.commit()
        raise ApiUnavailableError("Garmin integration is not configured") from exc
    except SyncAlreadyRunningError as exc:
        if exc.running_sync_run is None:
            raise ApiConflictError("Garmin sync is already running") from exc
        connection = repository.get_connection_for_user(current_user.id, connection.id) or connection
        return DataEnvelope(data=_connection_response(connection, sync_summary=exc.running_sync_run.summary))
    connection = repository.get_connection_for_user(current_user.id, connection.id) or connection
    daily_advice_run = _queue_daily_advice_after_sync(
        session, repository=repository, user_id=current_user.id, connection=connection,
    )
    return DataEnvelope(data=_connection_response(connection, sync_summary=sync_summary, daily_advice_run=daily_advice_run))


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


def _run_garmin_sync(
    *,
    repository: SqlAlchemyIntegrationRepository,
    session: Session,
    user_id: str,
    connection_id: str,
    resource_adapter: GarminResourceAdapter,
    sync_run_id: str | None = None,
) -> SyncSummary:
    return GarminInitialSyncHandler(
        integrations=repository,
        activities=SqlAlchemyActivityRepository(session),
        outbox=SqlAlchemyOutboxRepository(session),
        garmin=resource_adapter,
        athlete_profiles=SqlAlchemyAthleteRaceRepository(session),
        normalize_activity=lambda user_id, provider_connection_id, activity_payload: normalize_garmin_activity(
            user_id=user_id,
            provider_connection_id=provider_connection_id,
            payload=activity_payload,
        ),
        normalize_health=lambda user_id, health_payload: normalize_garmin_daily_health(
            user_id=user_id,
            payload=health_payload,
        ),
    ).handle(
        GarminInitialSyncCommand(
            user_id=user_id,
            connection_id=connection_id,
            as_of=datetime.now(timezone.utc),
            sync_run_id=sync_run_id,
        )
    )


def _require_admin_token(provided: str | None) -> None:
    configured = os.getenv("JOHNNY_ADMIN_TOKEN")
    if not configured or not provided or not compare_digest(provided, configured):
        raise ApiUnauthorizedError("Admin token required")


class _WebhookProviderAdapter:
    def __init__(self, payload: ProviderWebhookRequest) -> None:
        self._payload = payload

    def fetch(self, connection: IntegrationConnectionRef, cursor: dict[str, Any] | None = None) -> ProviderFetchResult:
        return ProviderFetchResult.create(
            activities=self._payload.activities,
            health=self._payload.health,
            cursor=self._payload.cursor,
        )


def _connection_response(
    connection: IntegrationConnectionRef,
    *,
    sync_summary=None,  # noqa: ANN001
    daily_advice_run: QueuedAgentRunResponse | None = None,
) -> IntegrationConnectionResponse:
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
        sync_status=connection.sync_status,
        last_sync_started_at=connection.last_sync_started_at,
        last_sync_completed_at=connection.last_sync_completed_at,
        last_sync_error=connection.last_sync_error,
        has_partial_failures=_has_partial_failures(sync_summary),
        sync_warning=_sync_warning(connection, sync_summary),
        sync_summary=SyncSummaryResponse(**sync_summary.to_payload()) if sync_summary is not None else None,
        daily_advice_run=daily_advice_run,
    )


def _queue_daily_advice_after_sync(
    session: Session, *, repository: SqlAlchemyIntegrationRepository,
    user_id: str, connection: IntegrationConnectionRef,
) -> QueuedAgentRunResponse | None:
    sync_run = repository.get_latest_sync_run_for_connection(connection.id)
    if sync_run is None or sync_run.status == "started":
        return None
    profile = SqlAlchemyAthleteRaceRepository(session).get_profile_for_user(user_id)
    timezone_name = profile.timezone if profile else "UTC"
    anchor_date = datetime.now(timezone.utc).astimezone(ZoneInfo(timezone_name)).date()
    queued = queue_after_completed_sync(
        user_id=user_id, anchor_date=anchor_date, sync_run=sync_run, connection=connection,
        training_plans=SqlAlchemyTrainingPlanRepository(session),
        advice=SqlAlchemyDailyAdviceRepository(session),
        queue_runs=lambda: _daily_advice_queue_handler(session),
    )
    if queued is None:
        return None
    return QueuedAgentRunResponse(
        run_id=queued.run.id, status=queued.run.status,
        workflow_name=queued.run.workflow_name, poll_url=queued.poll_url,
    )


def _daily_advice_queue_handler(session: Session) -> QueueAgentRunHandler:
    provider, model = resolve_queued_daily_advice_provider()
    return QueueAgentRunHandler(
        runs=SqlAlchemyAgentRunRepository(session), queue=SqlAlchemyAgentTaskQueue(session),
        prompt_version="running-companion-v1", provider=provider, model=model,
    )


def _has_partial_failures(sync_summary) -> bool:  # noqa: ANN001
    has_failure, has_successful_resource = _sync_summary_failure_state(sync_summary)
    return has_failure and has_successful_resource


def _sync_warning(connection: IntegrationConnectionRef, sync_summary) -> str | None:  # noqa: ANN001
    has_failure, has_successful_resource = _sync_summary_failure_state(sync_summary)
    if not has_failure:
        return None
    if connection.credential_status == "requires_reauth":
        return "Garmin connection requires reauth"
    if has_successful_resource:
        return "Some Garmin resources failed to sync"
    return "Garmin sync failed"


def _sync_summary_failure_state(sync_summary) -> tuple[bool, bool]:  # noqa: ANN001
    if sync_summary is None:
        return False, False
    resources = sync_summary.to_payload()["resources"]
    has_failure = any(int(bucket.get("failed", 0)) > 0 for bucket in resources.values())
    has_successful_resource = any(int(bucket.get("failed", 0)) == 0 for bucket in resources.values())
    return has_failure, has_successful_resource
