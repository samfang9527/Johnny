from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from src.application.interfaces.integrations_notifications import NotificationChannelGateway, NotificationStore
from src.domain.integrations_notifications import NotificationDelivery, NotificationIntent


ACTIVE_INTENT_STATUSES = {"pending", "retryable"}


@dataclass(frozen=True)
class CreateRecommendationNotificationCommand:
    user_id: str
    recommendation_id: str
    channel: str
    title: str
    rationale: str
    approval_url: str
    evidence_url: str
    scheduled_for: datetime | None = None


@dataclass(frozen=True)
class DeliverNotificationCommand:
    user_id: str
    intent_id: str


class CreateRecommendationNotificationIntentHandler:
    def __init__(self, *, notifications: NotificationStore) -> None:
        self._notifications = notifications

    def handle(self, command: CreateRecommendationNotificationCommand) -> NotificationIntent:
        existing = _find_active_intent(
            self._notifications.list_intents_for_user(command.user_id, limit=100, offset=0),
            recommendation_id=command.recommendation_id,
            channel=command.channel,
        )
        if existing is not None:
            return existing

        return self._notifications.create_intent(
            NotificationIntent.recommendation(
                user_id=command.user_id,
                recommendation_id=command.recommendation_id,
                channel=command.channel,
                scheduled_for=command.scheduled_for,
                payload=format_line_recommendation_payload(
                    title=command.title,
                    rationale=command.rationale,
                    approval_url=command.approval_url,
                    evidence_url=command.evidence_url,
                ),
            )
        )


class NotificationDeliveryHandler:
    def __init__(self, *, notifications: NotificationStore, gateway: NotificationChannelGateway, max_attempts: int = 3) -> None:
        self._notifications = notifications
        self._gateway = gateway
        self._max_attempts = max_attempts

    def handle(self, command: DeliverNotificationCommand) -> NotificationIntent:
        intent = self._notifications.get_intent_for_user(command.user_id, command.intent_id)
        if intent is None:
            raise ValueError("notification intent not found")
        result = self._gateway.deliver(intent)
        delivery = self._notifications.record_delivery(
            NotificationDelivery.from_gateway_result(notification_intent_id=intent.id or "", result=result)
        )
        if delivery.status == "succeeded":
            return self._notifications.mark_intent_delivered(intent.id or "")

        attempts = self._notifications.list_deliveries_for_intent(intent.id or "", limit=None, offset=0)
        if not delivery.response.get("retryable", False) or len(attempts) >= self._max_attempts:
            return self._notifications.mark_intent_failed(intent.id or "")
        return self._notifications.mark_intent_retryable(intent.id or "")


def format_line_recommendation_payload(
    *,
    title: str,
    rationale: str,
    approval_url: str,
    evidence_url: str,
) -> dict[str, str]:
    body = _truncate(f"Johnny: {title}", 72)
    reason = _truncate(rationale, 80)
    message = f"{body}\n{reason}\nReview: {approval_url}\nEvidence: {evidence_url}"
    return {
        "message": _truncate(message, 240),
        "approval_url": approval_url,
        "evidence_url": evidence_url,
    }


def _find_active_intent(
    intents: list[NotificationIntent],
    *,
    recommendation_id: str,
    channel: str,
) -> NotificationIntent | None:
    for intent in intents:
        if intent.recommendation_id == recommendation_id and intent.channel == channel and intent.status in ACTIVE_INTENT_STATUSES:
            return intent
    return None


def _truncate(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[: max(0, limit - 3)].rstrip() + "..."
