from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any


class DomainValidationError(ValueError):
    """Raised when integration or notification data cannot be persisted safely."""


@dataclass(frozen=True)
class IntegrationConnectionRef:
    id: str
    user_id: str
    provider: str
    provider_account_id: str | None = None
    credential_secret_ref: str | None = None
    credential_format: str | None = None
    credential_status: str = "active"
    status: str = "active"
    capabilities: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        if not self.id:
            raise DomainValidationError("connection id is required")
        if not self.user_id:
            raise DomainValidationError("user id is required")
        if not self.provider:
            raise DomainValidationError("provider is required")
        if self.status not in {"active", "replaced", "disconnected"}:
            raise DomainValidationError("integration connection status is not supported")
        if self.credential_secret_ref and _looks_like_raw_secret(self.credential_secret_ref):
            raise DomainValidationError("credential_secret_ref must reference a secret, not contain credentials")
        object.__setattr__(self, "capabilities", dict(self.capabilities or {}))

    @classmethod
    def create(
        cls,
        *,
        id: str,
        user_id: str,
        provider: str,
        provider_account_id: str | None = None,
        credential_secret_ref: str | None = None,
        credential_format: str | None = None,
        credential_status: str = "active",
        status: str = "active",
        capabilities: dict[str, Any] | None = None,
    ) -> IntegrationConnectionRef:
        return cls(
            id=id,
            user_id=user_id,
            provider=provider,
            provider_account_id=provider_account_id,
            credential_secret_ref=credential_secret_ref,
            credential_format=credential_format,
            credential_status=credential_status,
            status=status,
            capabilities=capabilities,
        )

    def to_safe_summary(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "provider": self.provider,
            "provider_account_id": self.provider_account_id,
            "credential_format": self.credential_format,
            "credential_status": self.credential_status,
            "status": self.status,
            "capabilities": dict(self.capabilities or {}),
        }


@dataclass(frozen=True)
class ProviderFetchResult:
    activities: tuple[dict[str, Any], ...]
    health: tuple[dict[str, Any], ...]
    cursor: dict[str, Any]

    @classmethod
    def create(
        cls,
        *,
        activities: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None = None,
        health: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None = None,
        cursor: dict[str, Any] | None = None,
    ) -> ProviderFetchResult:
        return cls(
            activities=tuple(dict(payload) for payload in activities or ()),
            health=tuple(dict(payload) for payload in health or ()),
            cursor=dict(cursor or {}),
        )


@dataclass(frozen=True)
class NormalizedProviderRecord:
    resource_type: str
    source_payload_id: str
    record: Any

    def __post_init__(self) -> None:
        if self.resource_type not in {"activity", "health"}:
            raise DomainValidationError("normalized provider resource type is not supported")
        if not self.source_payload_id:
            raise DomainValidationError("normalized provider source payload id is required")
        if self.record is None:
            raise DomainValidationError("normalized provider record is required")

    @classmethod
    def activity(cls, *, source_payload_id: str, record: Any) -> NormalizedProviderRecord:
        return cls(resource_type="activity", source_payload_id=source_payload_id, record=record)

    @classmethod
    def health(cls, *, source_payload_id: str, record: Any) -> NormalizedProviderRecord:
        return cls(resource_type="health", source_payload_id=source_payload_id, record=record)


@dataclass(frozen=True)
class SyncSummary:
    resources: dict[str, dict[str, Any]]

    @classmethod
    def empty(cls) -> SyncSummary:
        return cls(resources={})

    def record_fetched(self, resource_type: str, count: int = 1) -> SyncSummary:
        return self._increment(resource_type, "fetched", count)

    def record_stored(self, resource_type: str, count: int = 1) -> SyncSummary:
        return self._increment(resource_type, "stored", count)

    def record_duplicate(self, resource_type: str, count: int = 1) -> SyncSummary:
        return self._increment(resource_type, "duplicates", count)

    def record_failed(self, resource_type: str, error: str, count: int = 1) -> SyncSummary:
        resources = _copy_resources(self.resources)
        bucket = _bucket(resources, resource_type)
        bucket["failed"] += count
        bucket["errors"].append(_safe_error_summary(error))
        return SyncSummary(resources=resources)

    def to_payload(self) -> dict[str, Any]:
        return {"resources": _copy_resources(self.resources)}

    @classmethod
    def from_payload(cls, payload: dict[str, Any] | None) -> SyncSummary:
        resources = {}
        for resource_type, values in (payload or {}).get("resources", {}).items():
            bucket = _bucket(resources, resource_type)
            bucket["fetched"] = int(values.get("fetched", 0))
            bucket["stored"] = int(values.get("stored", 0))
            bucket["duplicates"] = int(values.get("duplicates", 0))
            bucket["failed"] = int(values.get("failed", 0))
            bucket["errors"] = list(values.get("errors", []))
        return cls(resources=resources)

    def _increment(self, resource_type: str, field: str, count: int) -> SyncSummary:
        if count < 0:
            raise DomainValidationError("sync summary count cannot be negative")
        resources = _copy_resources(self.resources)
        _bucket(resources, resource_type)[field] += count
        return SyncSummary(resources=resources)


@dataclass(frozen=True)
class SyncRun:
    id: str
    integration_connection_id: str
    status: str
    started_at: datetime
    finished_at: datetime | None = None
    summary: SyncSummary = SyncSummary.empty()

    def __post_init__(self) -> None:
        if not self.id:
            raise DomainValidationError("sync run id is required")
        if not self.integration_connection_id:
            raise DomainValidationError("sync run connection id is required")
        if self.status not in {"started", "succeeded", "failed"}:
            raise DomainValidationError("sync run status is not supported")

    @classmethod
    def start(cls, *, id: str, integration_connection_id: str, started_at: datetime) -> SyncRun:
        return cls(id=id, integration_connection_id=integration_connection_id, status="started", started_at=started_at)

    def complete(self, summary: SyncSummary, *, finished_at: datetime) -> SyncRun:
        return replace(self, status="succeeded", finished_at=finished_at, summary=summary)

    def fail(self, error: str, *, finished_at: datetime) -> SyncRun:
        return replace(
            self,
            status="failed",
            finished_at=finished_at,
            summary=SyncSummary.empty().record_failed("sync", error),
        )


@dataclass(frozen=True)
class OutboxEvent:
    topic: str
    payload: dict[str, Any]
    status: str = "pending"
    id: str | None = None
    published_at: datetime | None = None

    def __post_init__(self) -> None:
        if not self.topic:
            raise DomainValidationError("outbox topic is required")
        if self.status not in {"pending", "published"}:
            raise DomainValidationError("outbox status is not supported")
        object.__setattr__(self, "payload", dict(self.payload))

    @classmethod
    def activity_ingested(
        cls,
        *,
        user_id: str,
        activity_id: str,
        provider_connection_id: str,
        source_activity_id: str,
    ) -> OutboxEvent:
        return cls(
            topic="ActivityIngested",
            payload={
                "user_id": user_id,
                "activity_id": activity_id,
                "provider_connection_id": provider_connection_id,
                "source_activity_id": source_activity_id,
            },
        )


@dataclass(frozen=True)
class NotificationIntent:
    user_id: str
    recommendation_id: str | None
    channel: str
    status: str
    scheduled_for: datetime | None
    payload: dict[str, Any]
    id: str | None = None

    def __post_init__(self) -> None:
        if not self.user_id:
            raise DomainValidationError("notification user id is required")
        if not self.channel:
            raise DomainValidationError("notification channel is required")
        if self.status not in {"pending", "delivered", "retryable", "failed"}:
            raise DomainValidationError("notification status is not supported")
        object.__setattr__(self, "payload", dict(self.payload))

    @classmethod
    def recommendation(
        cls,
        *,
        user_id: str,
        recommendation_id: str,
        channel: str,
        payload: dict[str, Any],
        id: str | None = None,
        scheduled_for: datetime | None = None,
    ) -> NotificationIntent:
        return cls(
            id=id,
            user_id=user_id,
            recommendation_id=recommendation_id,
            channel=channel,
            status="pending",
            scheduled_for=scheduled_for,
            payload=payload,
        )


@dataclass(frozen=True)
class LineDeliveryResult:
    success: bool
    provider_message_id: str | None = None
    status_code: int | None = None
    response: dict[str, Any] | None = None
    retryable: bool = False

    @classmethod
    def success_response(cls, *, provider_message_id: str, response: dict[str, Any] | None = None) -> LineDeliveryResult:
        return cls(success=True, provider_message_id=provider_message_id, status_code=200, response=response or {}, retryable=False)

    @classmethod
    def failure(
        cls,
        *,
        status_code: int | None = None,
        response: dict[str, Any] | None = None,
        retryable: bool | None = None,
    ) -> LineDeliveryResult:
        should_retry = status_code is None or status_code >= 500 or status_code == 429 if retryable is None else retryable
        return cls(success=False, status_code=status_code, response=response or {}, retryable=should_retry)


@dataclass(frozen=True)
class NotificationDelivery:
    notification_intent_id: str
    status: str
    provider: str
    provider_message_id: str | None
    attempted_at: datetime | None
    response: dict[str, Any]
    id: str | None = None

    def __post_init__(self) -> None:
        if not self.notification_intent_id:
            raise DomainValidationError("delivery notification intent id is required")
        if self.status not in {"succeeded", "failed"}:
            raise DomainValidationError("delivery status is not supported")
        if not self.provider:
            raise DomainValidationError("delivery provider is required")
        object.__setattr__(self, "response", dict(self.response))

    @classmethod
    def from_gateway_result(
        cls,
        *,
        notification_intent_id: str,
        result: LineDeliveryResult,
        provider: str = "line",
        attempted_at: datetime | None = None,
        id: str | None = None,
    ) -> NotificationDelivery:
        response = dict(result.response or {})
        response["status_code"] = result.status_code
        response["retryable"] = result.retryable
        return cls(
            id=id,
            notification_intent_id=notification_intent_id,
            status="succeeded" if result.success else "failed",
            provider=provider,
            provider_message_id=result.provider_message_id,
            attempted_at=attempted_at,
            response=response,
        )


def _looks_like_raw_secret(value: str) -> bool:
    lowered = value.lower()
    return any(marker in lowered for marker in ("password", "token=", "refresh_token", "access_token", "{"))


def _safe_error_summary(error: str) -> str:
    lowered = error.lower()
    if any(marker in lowered for marker in ("password", "token", "secret", "credential")):
        return "credential or token details redacted"
    return error[:500]


def _bucket(resources: dict[str, dict[str, Any]], resource_type: str) -> dict[str, Any]:
    if not resource_type:
        raise DomainValidationError("sync summary resource type is required")
    if resource_type not in resources:
        resources[resource_type] = {"fetched": 0, "stored": 0, "duplicates": 0, "failed": 0, "errors": []}
    return resources[resource_type]


def _copy_resources(resources: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {
        resource_type: {
            "fetched": int(values.get("fetched", 0)),
            "stored": int(values.get("stored", 0)),
            "duplicates": int(values.get("duplicates", 0)),
            "failed": int(values.get("failed", 0)),
            "errors": list(values.get("errors", [])),
        }
        for resource_type, values in resources.items()
    }
