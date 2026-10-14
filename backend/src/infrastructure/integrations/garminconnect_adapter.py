from __future__ import annotations

from collections.abc import Callable
from datetime import date, timedelta
from typing import Any, NoReturn, Protocol

from src.application.interfaces.integrations_notifications import IntegrationCredentialStore
from src.application.integrations import (
    GARMIN_CREDENTIAL_FORMAT,
    GarminAccountProfile,
    GarminAuthenticationError,
    GarminCredentialBlockedError,
    GarminIntegrationConfigurationError,
    GarminRateLimitError,
    GarminResourceFetchResult,
    GarminTemporarySyncError,
)
from src.domain.integrations_notifications import IntegrationConnectionRef, IntegrationCredential
from src.infrastructure.security.integration_credentials import CredentialCipher


class GarminClient(Protocol):
    client: Any

    def login(self, tokenstore: str | None = None) -> tuple[str | None, str | None]:
        ...

    def get_heart_rate_zones(self) -> list[dict[str, Any]]: ...

    def get_lactate_threshold(self) -> dict[str, Any]: ...

    def get_user_profile(self) -> dict[str, Any]:
        ...

    def get_userprofile_settings(self) -> dict[str, Any]:
        ...

    def get_activities_by_date(
        self,
        startdate: str,
        enddate: str | None = None,
        activitytype: str | None = None,
        sortorder: str | None = None,
    ) -> list[dict[str, Any]]:
        ...

    def get_sleep_data(self, cdate: str) -> dict[str, Any]:
        ...

    def get_hrv_data(self, cdate: str) -> dict[str, Any] | None:
        ...

    def get_rhr_day(self, cdate: str) -> dict[str, Any]:
        ...

    def get_stress_data(self, cdate: str) -> dict[str, Any]:
        ...

    def get_body_battery(self, startdate: str, enddate: str | None = None) -> list[dict[str, Any]]:
        ...


GarminFactory = Callable[..., GarminClient]


class GarminConnectLoginAdapter:
    def __init__(self, *, garmin_factory: GarminFactory | None = None) -> None:
        self._garmin_factory = garmin_factory or _default_garmin_factory

    def exchange_credentials(self, *, email: str, password: str, region: str) -> GarminAccountProfile:
        api = self._garmin_factory(
            email=email,
            password=password,
            is_cn=region == "china",
            return_on_mfa=True,
        )
        try:
            mfa_status, _ = api.login()
        except Exception as exc:  # noqa: BLE001
            _raise_login_error(exc)
        if mfa_status:
            raise GarminAuthenticationError("Garmin Connect requires manual token import")

        try:
            profile = _safe_dict(api.get_user_profile())
            settings = _safe_dict(_call_optional(api.get_userprofile_settings))
            session_payload = _dump_session(api)
        except GarminIntegrationConfigurationError:
            raise
        except Exception as exc:  # noqa: BLE001
            _raise_login_error(exc)
        provider_account_id = _provider_account_id(profile)
        if not provider_account_id:
            raise GarminAuthenticationError("Garmin Connect profile did not include account identity")
        return GarminAccountProfile(
            provider_account_id=provider_account_id,
            display_name=_display_name(profile),
            session_payload=session_payload,
            timezone=_timezone_name(profile, settings),
        )


class GarminConnectResourceAdapter:
    def __init__(
        self,
        *,
        credentials: IntegrationCredentialStore,
        cipher: CredentialCipher,
        garmin_factory: GarminFactory | None = None,
    ) -> None:
        self._credentials = credentials
        self._cipher = cipher
        self._garmin_factory = garmin_factory or _default_garmin_factory

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
        credential = self._credentials.get_credential_for_connection(connection.id)
        if credential is None:
            raise GarminCredentialBlockedError("Garmin credential is missing")

        session_payload = self._cipher.decrypt(credential.encrypted_payload)
        api = self._garmin_factory(is_cn=_is_china_region(connection), return_on_mfa=True)
        try:
            mfa_status, _ = api.login(session_payload)
        except Exception as exc:  # noqa: BLE001
            _raise_resource_error(exc)
        if mfa_status:
            raise GarminCredentialBlockedError("Garmin Connect requires manual token import")

        try:
            result = self._fetch_resource(api, resource_type, start_date, end_date)
        except Exception as exc:  # noqa: BLE001
            _raise_resource_error(exc)
        self._save_refreshed_session(connection, credential, api)
        return result

    def _fetch_resource(
        self,
        api: GarminClient,
        resource_type: str,
        start_date: date,
        end_date: date,
    ) -> GarminResourceFetchResult:
        start_text = start_date.isoformat()
        end_text = end_date.isoformat()
        if resource_type == "heart_rate_zones":
            return GarminResourceFetchResult(items=[{"profiles": api.get_heart_rate_zones()}])
        if resource_type == "lactate_threshold":
            return GarminResourceFetchResult(items=[api.get_lactate_threshold()])
        if resource_type == "activities":
            items = api.get_activities_by_date(start_text, end_text, sortorder="asc")
            return GarminResourceFetchResult(items=items, cursor=_date_cursor(start_date, end_date))
        if resource_type == "body_battery":
            items = [
                {"calendarDate": _item_date(item), "get_body_battery": item}
                for item in api.get_body_battery(start_text, end_text)
                if _item_date(item)
            ]
            return GarminResourceFetchResult(items=items, cursor=_date_cursor(start_date, end_date))
        if resource_type not in _DAILY_RESOURCE_METHODS:
            raise GarminIntegrationConfigurationError(f"Garmin resource is not supported: {resource_type}")

        items: list[dict[str, Any]] = []
        method_name = _DAILY_RESOURCE_METHODS[resource_type]
        for day in _each_day(start_date, end_date):
            day_text = day.isoformat()
            payload = _call_daily_resource(api, method_name, day_text)
            if payload:
                items.append({"calendarDate": day_text, method_name: payload})
        return GarminResourceFetchResult(items=items, cursor=_date_cursor(start_date, end_date))

    def _save_refreshed_session(
        self,
        connection: IntegrationConnectionRef,
        credential: IntegrationCredential,
        api: GarminClient,
    ) -> None:
        refreshed_payload = _dump_session(api)
        encrypted_payload = self._cipher.encrypt(refreshed_payload)
        metadata = dict(credential.lifecycle_metadata or {})
        metadata.setdefault("source", "garminconnect")
        self._credentials.upsert_credential(
            IntegrationCredential.create(
                connection_id=connection.id,
                credential_format=GARMIN_CREDENTIAL_FORMAT,
                encrypted_payload=encrypted_payload,
                key_id=self._cipher.key_id,
                lifecycle_metadata=metadata,
            )
        )


_DAILY_RESOURCE_METHODS = {
    "sleep": "get_sleep_data",
    "hrv": "get_hrv_data",
    "resting_heart_rate": "get_rhr_day",
    "stress": "get_stress_data",
}

def _default_garmin_factory(**kwargs) -> GarminClient:  # noqa: ANN003
    try:
        from garminconnect import Garmin
    except ImportError as exc:
        raise GarminIntegrationConfigurationError("python-garminconnect is not installed") from exc
    return Garmin(**kwargs)


def _call_daily_resource(api: GarminClient, method_name: str, day_text: str) -> dict[str, Any] | None:
    try:
        return _safe_dict(getattr(api, method_name)(day_text))
    except Exception as exc:  # noqa: BLE001
        if _is_not_found_error(exc):
            return None
        raise


def _call_optional(call: Callable[[], Any]) -> Any:
    try:
        return call()
    except Exception:  # noqa: BLE001
        return {}


def _raise_login_error(exc: Exception) -> NoReturn:
    if _is_rate_limit_error(exc):
        raise GarminAuthenticationError("Garmin Connect login is rate limited") from exc
    if _is_authentication_error(exc):
        raise GarminAuthenticationError("Garmin Connect credentials could not be verified") from exc
    raise GarminIntegrationConfigurationError("Garmin Connect login failed") from exc


def _raise_resource_error(exc: Exception) -> NoReturn:
    if _is_rate_limit_error(exc):
        raise GarminRateLimitError() from exc
    if _is_authentication_error(exc):
        raise GarminCredentialBlockedError() from exc
    if _is_temporary_error(exc):
        raise GarminTemporarySyncError() from exc
    raise exc


def _is_authentication_error(exc: Exception) -> bool:
    text = _exception_text(exc)
    return any(marker in text for marker in ("authentication", "unauthorized", "forbidden", "401", "403", "mfa", "2fa"))


def _is_rate_limit_error(exc: Exception) -> bool:
    text = _exception_text(exc)
    return any(marker in text for marker in ("too many requests", "rate limit", "429"))


def _is_temporary_error(exc: Exception) -> bool:
    text = _exception_text(exc)
    return any(marker in text for marker in ("temporarily blocked", "temporary block", "502", "503", "504", "retry-after", "retry after"))


def _is_not_found_error(exc: Exception) -> bool:
    text = _exception_text(exc)
    return "notfound" in text or "not found" in text or "404" in text


def _exception_text(exc: Exception) -> str:
    return f"{type(exc).__name__} {exc}".lower()


def _provider_account_id(profile: dict[str, Any]) -> str:
    value = profile.get("profileId") or profile.get("userId") or profile.get("id")
    return str(value) if value else ""


def _display_name(profile: dict[str, Any]) -> str | None:
    value = profile.get("displayName") or profile.get("fullName") or profile.get("userName")
    return str(value) if value else None


def _timezone_name(profile: dict[str, Any], settings: dict[str, Any]) -> str | None:
    user_data = settings.get("userData") if isinstance(settings.get("userData"), dict) else {}
    value = (
        user_data.get("timeZone")
        or user_data.get("timeZoneId")
        or settings.get("timeZone")
        or settings.get("timeZoneId")
        or profile.get("timeZone")
        or profile.get("timeZoneId")
    )
    return str(value) if value else None


def _dump_session(api: GarminClient) -> str:
    client = getattr(api, "client", None)
    dumps = getattr(client, "dumps", None)
    if not callable(dumps):
        raise GarminIntegrationConfigurationError("Garmin client does not support inline token serialization")
    return str(dumps())


def _safe_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _is_china_region(connection: IntegrationConnectionRef) -> bool:
    return (connection.provider_metadata or {}).get("region") == "china"


def _date_cursor(start_date: date, end_date: date) -> dict[str, str]:
    return {"start_date": start_date.isoformat(), "end_date": end_date.isoformat()}


def _item_date(item: dict[str, Any]) -> str:
    value = item.get("calendarDate") or item.get("date") or item.get("day")
    return str(value) if value else ""


def _each_day(start_date: date, end_date: date):
    current = start_date
    while current <= end_date:
        yield current
        current += timedelta(days=1)
