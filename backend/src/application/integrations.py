from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Callable, Protocol
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from src.application.interfaces.integrations_notifications import (
    IntegrationCredentialStore,
    IntegrationStore,
    OutboxStore,
    ProviderActivityStore,
    ProviderAdapter,
)
from src.application.interfaces.athlete_race_store import AthleteProfileStore
from src.domain.activity_health import CompletedActivity, DailyHealthMetrics, DomainValidationError as ActivityHealthValidationError
from src.domain.integrations_notifications import IntegrationConnectionRef, IntegrationCredential, OutboxEvent, SyncAlreadyRunningError, SyncSummary


logger = logging.getLogger(__name__)

GARMIN_PROVIDER = "garmin_connect"
GARMIN_AUTH_SCHEME = "garminconnect_tokenstore"
GARMIN_CREDENTIAL_FORMAT = "garminconnect-session-json"
GARMIN_SYNC_RESOURCES = ("activities", "sleep", "hrv", "resting_heart_rate", "stress", "body_battery")


class ProviderAccountAlreadyConnectedError(ValueError):
    pass


class GarminAuthenticationError(ValueError):
    pass


class GarminIntegrationConfigurationError(RuntimeError):
    pass


class GarminCredentialBlockedError(RuntimeError):
    pass


class _GarminBackoffSyncError(RuntimeError):
    safe_summary = "Garmin sync failed"

    def __init__(
        self,
        message: str | None = None,
        *,
        retry_after_seconds: int | None = None,
        backoff_until: str | None = None,
    ) -> None:
        super().__init__(message or self.safe_summary)
        self.retry_after_seconds = retry_after_seconds
        self.backoff_until = backoff_until

    def backoff_metadata(self) -> dict[str, int | str]:
        metadata: dict[str, int | str] = {}
        if self.retry_after_seconds is not None:
            metadata["retry_after_seconds"] = self.retry_after_seconds
        if self.backoff_until is not None:
            metadata["backoff_until"] = self.backoff_until
        return metadata


class GarminRateLimitError(_GarminBackoffSyncError):
    safe_summary = "Garmin rate limit exceeded"


class GarminTemporarySyncError(_GarminBackoffSyncError):
    safe_summary = "Garmin temporary sync failure"


class SyncConnectionLifecycleStore(Protocol):
    def get_connection_by_provider_account(self, provider: str, provider_account_id: str) -> IntegrationConnectionRef | None: ...

    def replace_active_connections_for_user(self, user_id: str, *, except_connection_id: str | None = None) -> None: ...

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
    ) -> IntegrationConnectionRef: ...

    def reactivate_connection(
        self,
        connection_id: str,
        *,
        credential_secret_ref: str | None = None,
        credential_format: str | None = None,
        capabilities: dict | None = None,
        provider_metadata: dict | None = None,
        provider_display_name: str | None = None,
        auth_scheme: str | None = None,
    ) -> IntegrationConnectionRef: ...

    def reset_resource_cursors(self, integration_connection_id: str) -> None: ...

    def get_connection_for_user(self, user_id: str, connection_id: str) -> IntegrationConnectionRef | None: ...

    def disconnect_connection(self, connection_id: str) -> IntegrationConnectionRef: ...

    def mark_connection_credentials_active(self, connection_id: str, *, credential_format: str) -> IntegrationConnectionRef: ...


class GarminLoginAdapter(Protocol):
    def exchange_credentials(self, *, email: str, password: str, region: str) -> GarminAccountProfile:
        ...


class CredentialCipher(Protocol):
    key_id: str

    def encrypt(self, plaintext: str) -> str:
        ...


class GarminResourceAdapter(Protocol):
    def fetch_resource(
        self,
        *,
        connection: IntegrationConnectionRef,
        resource_type: str,
        start_date: date,
        end_date: date,
        timezone_name: str,
        cursor: dict | None,
    ) -> GarminResourceFetchResult:
        ...


@dataclass(frozen=True)
class ProviderSyncCommand:
    user_id: str
    connection_id: str


@dataclass(frozen=True)
class GarminInitialSyncCommand:
    user_id: str
    connection_id: str
    as_of: datetime | None = None
    sync_run_id: str | None = None


@dataclass(frozen=True)
class GarminResourceFetchResult:
    items: tuple[dict, ...] = ()
    cursor: dict | None = None

    def __init__(self, items: list[dict] | tuple[dict, ...] | None = None, cursor: dict | None = None) -> None:
        object.__setattr__(self, "items", tuple(dict(item) for item in items or ()))
        object.__setattr__(self, "cursor", dict(cursor or {}))


@dataclass(frozen=True)
class GarminAccountProfile:
    provider_account_id: str
    display_name: str | None
    session_payload: str
    timezone: str | None = None


@dataclass(frozen=True)
class ConnectGarminAccountCommand:
    user_id: str
    email: str
    password: str
    region: str


@dataclass(frozen=True)
class DisconnectGarminConnectionCommand:
    user_id: str
    connection_id: str


@dataclass(frozen=True)
class AdminImportGarminTokenCommand:
    user_id: str
    connection_id: str
    session_payload: str


@dataclass(frozen=True)
class ConnectSyncProviderCommand:
    user_id: str
    provider: str
    provider_account_id: str
    credential_secret_ref: str | None = None
    provider_display_name: str | None = None
    auth_scheme: str = "oauth2"
    credential_format: str | None = None
    capabilities: dict | None = None
    provider_metadata: dict | None = None


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
                credential_format=command.credential_format,
                capabilities=command.capabilities,
                provider_metadata=command.provider_metadata,
                provider_display_name=command.provider_display_name,
                auth_scheme=command.auth_scheme,
            )
            self._integrations.reset_resource_cursors(reactivated.id)
            return reactivated

        self._integrations.replace_active_connections_for_user(command.user_id)
        return self._integrations.create_connection(
            user_id=command.user_id,
            provider=command.provider,
            provider_account_id=command.provider_account_id,
            provider_display_name=command.provider_display_name,
            auth_scheme=command.auth_scheme,
            credential_secret_ref=command.credential_secret_ref,
            credential_format=command.credential_format,
            capabilities=command.capabilities,
            provider_metadata=command.provider_metadata,
        )


class ConnectGarminAccountHandler:
    def __init__(
        self,
        *,
        integrations: SyncConnectionLifecycleStore,
        credentials: IntegrationCredentialStore,
        garmin: GarminLoginAdapter,
        cipher: CredentialCipher,
    ) -> None:
        self._integrations = integrations
        self._credentials = credentials
        self._garmin = garmin
        self._cipher = cipher

    def handle(self, command: ConnectGarminAccountCommand) -> IntegrationConnectionRef:
        if command.region not in {"global", "china"}:
            raise ValueError("Garmin region is not supported")

        profile = self._garmin.exchange_credentials(
            email=command.email,
            password=command.password,
            region=command.region,
        )
        existing = self._integrations.get_connection_by_provider_account(GARMIN_PROVIDER, profile.provider_account_id)
        if existing is not None and existing.user_id == command.user_id and existing.sync_status == "running":
            raise SyncAlreadyRunningError()
        encrypted_payload = self._cipher.encrypt(profile.session_payload)
        connection = ConnectSyncProviderHandler(integrations=self._integrations).handle(
            ConnectSyncProviderCommand(
                user_id=command.user_id,
                provider=GARMIN_PROVIDER,
                provider_account_id=profile.provider_account_id,
                provider_display_name=profile.display_name,
                auth_scheme=GARMIN_AUTH_SCHEME,
                credential_format=GARMIN_CREDENTIAL_FORMAT,
                capabilities={"activities": True, "health": True},
                provider_metadata=_garmin_provider_metadata(region=command.region, timezone=profile.timezone),
            )
        )
        self._credentials.upsert_credential(
            IntegrationCredential.create(
                connection_id=connection.id,
                credential_format=GARMIN_CREDENTIAL_FORMAT,
                encrypted_payload=encrypted_payload,
                key_id=self._cipher.key_id,
                lifecycle_metadata=_garmin_credential_metadata(
                    region=command.region,
                    display_name=profile.display_name,
                    timezone=profile.timezone,
                ),
            )
        )
        return connection


class DisconnectGarminConnectionHandler:
    def __init__(
        self,
        *,
        integrations: SyncConnectionLifecycleStore,
    ) -> None:
        self._integrations = integrations

    def handle(self, command: DisconnectGarminConnectionCommand) -> IntegrationConnectionRef:
        connection = self._integrations.get_connection_for_user(command.user_id, command.connection_id)
        if connection is None or connection.provider != GARMIN_PROVIDER:
            raise ValueError("integration connection not found")
        return self._integrations.disconnect_connection(connection.id)


class AdminImportGarminTokenHandler:
    def __init__(
        self,
        *,
        integrations: SyncConnectionLifecycleStore,
        credentials: IntegrationCredentialStore,
        cipher: CredentialCipher,
    ) -> None:
        self._integrations = integrations
        self._credentials = credentials
        self._cipher = cipher

    def handle(self, command: AdminImportGarminTokenCommand) -> IntegrationConnectionRef:
        connection = self._integrations.get_connection_for_user(command.user_id, command.connection_id)
        if connection is None or connection.provider != GARMIN_PROVIDER:
            raise ValueError("integration connection not found")
        if connection.sync_status == "running":
            raise SyncAlreadyRunningError()
        encrypted_payload = self._cipher.encrypt(command.session_payload)
        self._credentials.upsert_credential(
            IntegrationCredential.create(
                connection_id=connection.id,
                credential_format=GARMIN_CREDENTIAL_FORMAT,
                encrypted_payload=encrypted_payload,
                key_id=self._cipher.key_id,
                lifecycle_metadata={"source": "admin_import"},
            )
        )
        return self._integrations.mark_connection_credentials_active(
            connection.id,
            credential_format=GARMIN_CREDENTIAL_FORMAT,
        )


class GarminInitialSyncHandler:
    def __init__(
        self,
        *,
        integrations: IntegrationStore,
        activities: ProviderActivityStore,
        outbox: OutboxStore,
        garmin: GarminResourceAdapter,
        athlete_profiles: AthleteProfileStore,
        normalize_activity: Callable[[str, str, dict], CompletedActivity],
        normalize_health: Callable[[str, dict], DailyHealthMetrics],
    ) -> None:
        self._integrations = integrations
        self._activities = activities
        self._outbox = outbox
        self._garmin = garmin
        self._athlete_profiles = athlete_profiles
        self._normalize_activity = normalize_activity
        self._normalize_health = normalize_health

    def handle(self, command: GarminInitialSyncCommand) -> SyncSummary:
        connection = self._integrations.get_connection_for_user(command.user_id, command.connection_id)
        if connection is None:
            raise ValueError("integration connection not found")
        if connection.credential_status == "requires_reauth":
            summary = SyncSummary.empty().record_failed("sync", "Garmin connection requires reauth")
            _log_garmin_sync_failure(
                "Garmin sync skipped because connection requires reauth",
                connection_id=connection.id,
                sync_run_id=command.sync_run_id,
                resource_type="sync",
                error="Garmin connection requires reauth",
            )
            if command.sync_run_id is not None:
                self._integrations.complete_sync_run(command.sync_run_id, summary, status="failed")
            return summary

        sync_run_id = command.sync_run_id
        if sync_run_id is None:
            sync_run_id = self._integrations.start_sync_run(connection.id).id
        timezone_name = self._timezone_name(command.user_id, connection)
        end_date = _local_date(command.as_of or datetime.now(timezone.utc), timezone_name)
        start_date = end_date - timedelta(days=29)
        summary = SyncSummary.empty()
        sync_status = "succeeded"

        for resource_type in GARMIN_SYNC_RESOURCES:
            cursor = self._integrations.get_resource_cursor(connection.id, resource_type)
            try:
                result = self._garmin.fetch_resource(
                    connection=connection,
                    resource_type=resource_type,
                    start_date=start_date,
                    end_date=end_date,
                    timezone_name=timezone_name,
                    cursor=cursor,
                )
                summary = summary.record_fetched(resource_type, len(result.items))
                failed_before = summary.failed_count(resource_type)
                summary = self._store_resource(command.user_id, connection.id, resource_type, result.items, summary)
                if summary.failed_count(resource_type) == failed_before:
                    self._integrations.upsert_resource_cursor(
                        connection.id,
                        resource_type,
                        result.cursor or {},
                        sync_from=_start_of_day(start_date),
                        sync_until=_end_of_day(end_date),
                    )
            except GarminCredentialBlockedError as exc:
                summary = summary.record_failed(resource_type, "Garmin connection requires reauth")
                _log_garmin_sync_failure(
                    "Garmin sync resource requires reauth",
                    connection_id=connection.id,
                    sync_run_id=sync_run_id,
                    resource_type=resource_type,
                    error=_safe_log_error(exc),
                )
                self._integrations.mark_connection_requires_reauth(
                    connection.id,
                    summary.to_payload()["resources"][resource_type]["errors"][-1],
                )
                sync_status = "failed"
                break
            except _GarminBackoffSyncError as exc:
                summary = summary.record_failed(resource_type, exc.safe_summary, backoff=exc.backoff_metadata())
                _log_garmin_sync_failure(
                    "Garmin sync resource failed with backoff",
                    connection_id=connection.id,
                    sync_run_id=sync_run_id,
                    resource_type=resource_type,
                    error=_safe_log_error(exc),
                    backoff=exc.backoff_metadata(),
                )
                sync_status = "failed"
                break
            except GarminIntegrationConfigurationError:
                raise
            except Exception as exc:  # noqa: BLE001
                classified = _classify_garmin_sync_exception(exc)
                if isinstance(classified, GarminCredentialBlockedError):
                    summary = summary.record_failed(resource_type, "Garmin connection requires reauth")
                    _log_garmin_sync_failure(
                        "Garmin sync resource classified as requiring reauth",
                        connection_id=connection.id,
                        sync_run_id=sync_run_id,
                        resource_type=resource_type,
                        error=_safe_log_error(exc),
                    )
                    self._integrations.mark_connection_requires_reauth(
                        connection.id,
                        summary.to_payload()["resources"][resource_type]["errors"][-1],
                    )
                    sync_status = "failed"
                    break
                if isinstance(classified, _GarminBackoffSyncError):
                    summary = summary.record_failed(resource_type, classified.safe_summary, backoff=classified.backoff_metadata())
                    _log_garmin_sync_failure(
                        "Garmin sync resource classified as temporary failure",
                        connection_id=connection.id,
                        sync_run_id=sync_run_id,
                        resource_type=resource_type,
                        error=_safe_log_error(exc),
                        backoff=classified.backoff_metadata(),
                    )
                    sync_status = "failed"
                    break
                summary = summary.record_failed(resource_type, "Garmin resource sync failed")
                _log_garmin_sync_failure(
                    "Garmin sync resource failed",
                    connection_id=connection.id,
                    sync_run_id=sync_run_id,
                    resource_type=resource_type,
                    error=_safe_log_error(exc),
                    level="exception",
                )

        self._integrations.complete_sync_run(sync_run_id, summary, status=sync_status)
        return summary

    def _store_resource(
        self,
        user_id: str,
        connection_id: str,
        resource_type: str,
        items: tuple[dict, ...],
        summary: SyncSummary,
    ) -> SyncSummary:
        if resource_type == "activities":
            return self._store_activities(user_id, connection_id, items, summary)
        return self._store_health_resource(user_id, connection_id, resource_type, items, summary)

    def _store_activities(
        self,
        user_id: str,
        connection_id: str,
        items: tuple[dict, ...],
        summary: SyncSummary,
    ) -> SyncSummary:
        failures: dict[str, _ProviderRecordIssue] = {}
        for payload in items:
            try:
                activity = self._normalize_activity(user_id, connection_id, payload)
                existing = self._activities.get_activity_by_provider_identifier(
                    user_id,
                    connection_id,
                    activity.source_activity_id or "",
                )
                if existing is not None:
                    summary = summary.record_duplicate("activities")
                    continue
                saved = self._activities.save_activity(user_id, activity)
                if saved is None:
                    summary = summary.record_duplicate("activities")
                    continue
                summary = summary.record_stored("activities")
                self._outbox.create_event(
                    OutboxEvent.activity_ingested(
                        user_id=user_id,
                        activity_id=saved.id or "",
                        provider_connection_id=connection_id,
                        source_activity_id=activity.source_activity_id or "",
                    )
                )
            except Exception as exc:  # noqa: BLE001
                summary = summary.record_failed("activities", "Garmin activity import failed")
                _record_provider_record_issue(
                    failures,
                    reason_code=_provider_record_error_code(exc),
                    error=_safe_log_error(exc),
                    sample=_activity_skip_sample(payload),
                )
        _log_provider_record_issues(connection_id=connection_id, resource_type="activities", issues=failures, skipped=False)
        return summary

    def _store_health_resource(
        self,
        user_id: str,
        connection_id: str,
        resource_type: str,
        items: tuple[dict, ...],
        summary: SyncSummary,
    ) -> SyncSummary:
        skipped: dict[str, _ProviderRecordIssue] = {}
        failures: dict[str, _ProviderRecordIssue] = {}
        for payload in items:
            try:
                metrics = self._normalize_health(user_id, payload)
                self._activities.save_daily_health_metrics(user_id, metrics)
                summary = summary.record_stored(resource_type)
            except Exception as exc:  # noqa: BLE001
                reason_code = _skippable_health_record_error_code(exc)
                if reason_code is not None:
                    _record_provider_record_issue(
                        skipped,
                        reason_code=reason_code,
                        error=_safe_log_error(exc),
                        sample=_health_skip_sample(payload),
                    )
                    continue
                summary = summary.record_failed(resource_type, "Garmin health import failed")
                _record_provider_record_issue(
                    failures,
                    reason_code=_provider_record_error_code(exc),
                    error=_safe_log_error(exc),
                    sample=_health_skip_sample(payload),
                )
        _log_provider_record_issues(connection_id=connection_id, resource_type=resource_type, issues=skipped, skipped=True)
        _log_provider_record_issues(connection_id=connection_id, resource_type=resource_type, issues=failures, skipped=False)
        return summary

    def _timezone_name(self, user_id: str, connection: IntegrationConnectionRef) -> str:
        profile = self._athlete_profiles.get_profile_for_user(user_id)
        if profile is not None and _valid_timezone(profile.timezone):
            return profile.timezone
        provider_timezone = (connection.provider_metadata or {}).get("timezone")
        if provider_timezone and _valid_timezone(str(provider_timezone)):
            return str(provider_timezone)
        return "UTC"


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


def _garmin_provider_metadata(*, region: str, timezone: str | None) -> dict:
    metadata = {"region": region}
    if timezone:
        metadata["timezone"] = timezone
    return metadata


def _garmin_credential_metadata(*, region: str, display_name: str | None, timezone: str | None) -> dict:
    metadata = {"region": region}
    if display_name:
        metadata["display_name"] = display_name
    if timezone:
        metadata["timezone"] = timezone
    return metadata


def _local_date(value: datetime, timezone_name: str) -> date:
    try:
        local_zone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        local_zone = timezone.utc
    return value.astimezone(local_zone).date()


def _start_of_day(value: date) -> datetime:
    return datetime(value.year, value.month, value.day, tzinfo=timezone.utc)


def _end_of_day(value: date) -> datetime:
    return _start_of_day(value) + timedelta(days=1)


def _valid_timezone(timezone_name: str) -> bool:
    try:
        ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        return False
    return True


@dataclass
class _ProviderRecordIssue:
    reason_code: str
    error: str
    sample: dict[str, str]
    count: int = 0


def _record_provider_record_issue(
    issues: dict[str, _ProviderRecordIssue],
    *,
    reason_code: str,
    error: str,
    sample: dict[str, str],
) -> None:
    if reason_code not in issues:
        issues[reason_code] = _ProviderRecordIssue(reason_code=reason_code, error=error, sample=sample)
    issues[reason_code].count += 1


def _log_provider_record_issues(
    *,
    connection_id: str,
    resource_type: str,
    issues: dict[str, _ProviderRecordIssue],
    skipped: bool,
) -> None:
    for issue in issues.values():
        _log_garmin_sync_failure(
            "Garmin sync skipped provider records" if skipped else "Garmin sync failed provider records",
            connection_id=connection_id,
            sync_run_id=None,
            resource_type=resource_type,
            error=issue.error,
            reason_code=issue.reason_code,
            count=issue.count,
            sample=issue.sample,
        )


def _log_garmin_sync_failure(
    message: str,
    *,
    connection_id: str | None,
    sync_run_id: str | None,
    resource_type: str,
    error: str,
    backoff: dict[str, int | str] | None = None,
    reason_code: str | None = None,
    count: int | None = None,
    sample: dict[str, str] | None = None,
    level: str = "warning",
) -> None:
    extra = {
        "provider": GARMIN_PROVIDER,
        "connection_id": connection_id,
        "sync_run_id": sync_run_id,
        "resource_type": resource_type,
        "error": error,
    }
    if backoff:
        extra["backoff"] = backoff
    if reason_code:
        extra["reason_code"] = reason_code
    if count is not None:
        extra["count"] = count
    if sample:
        extra["sample"] = sample
    if level == "exception":
        logger.exception(message, extra=extra)
        return
    logger.warning(message, extra=extra)


def _safe_log_error(exc: Exception) -> str:
    detail = f"{type(exc).__name__}: {exc}"
    if _looks_sensitive(detail):
        return f"{type(exc).__name__}: credential or token details redacted"
    return detail[:500]


def _looks_sensitive(value: str) -> bool:
    normalized = value.lower()
    return any(
        marker in normalized
        for marker in (
            "access_token",
            "refresh_token",
            "oauth",
            "cookie",
            "session",
            "sid",
            "tokenstore",
            "password",
            "secret",
            "jwt",
        )
    )


def _skippable_health_record_error_code(exc: Exception) -> str | None:
    if isinstance(exc, ActivityHealthValidationError) and str(exc) == "at least one health metric value is required":
        return "empty_supported_health_metrics"
    return None


def _provider_record_error_code(exc: Exception) -> str:
    if isinstance(exc, ActivityHealthValidationError):
        return _reason_code_from_message(str(exc))
    if isinstance(exc, KeyError):
        return "missing_required_provider_field"
    if isinstance(exc, ValueError):
        return "invalid_provider_value"
    return "provider_record_import_error"


def _reason_code_from_message(message: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "_", message.lower()).strip("_")
    return normalized or "provider_record_validation_error"


def _activity_skip_sample(payload: dict) -> dict[str, str]:
    return _safe_sample(payload, "activityId", "activityName")


def _health_skip_sample(payload: dict) -> dict[str, str]:
    return _safe_sample(payload, "calendarDate")


def _safe_sample(payload: dict, *keys: str) -> dict[str, str]:
    sample: dict[str, str] = {}
    for key in keys:
        value = payload.get(key)
        if value is not None:
            sample[key] = str(value)[:120]
    return sample


def _classify_garmin_sync_exception(exc: Exception) -> Exception | None:
    message = f"{type(exc).__name__} {exc}".lower()
    if any(marker in message for marker in ("429", "rate limit", "too many requests")):
        return GarminRateLimitError(retry_after_seconds=_retry_after_seconds(message))
    if any(marker in message for marker in ("temporarily blocked", "temporary block", "retry-after", "retry after", "502", "503", "504")):
        return GarminTemporarySyncError(retry_after_seconds=_retry_after_seconds(message))
    if any(marker in message for marker in ("mfa", "2fa", "unauthorized", "forbidden", "401", "403", "login", "reauth", "expired", "revoked")):
        return GarminCredentialBlockedError()
    return None


def _retry_after_seconds(message: str) -> int | None:
    match = re.search(r"retry[- ]after[:= ]+(\d+)", message)
    if match is None:
        return None
    return int(match.group(1))
