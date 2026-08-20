from dataclasses import replace
from datetime import datetime, timezone

from src.application.notifications import (
    CreateRecommendationNotificationCommand,
    CreateRecommendationNotificationIntentHandler,
    DeliverNotificationCommand,
    NotificationDeliveryHandler,
    format_line_recommendation_payload,
)
from src.domain.integrations_notifications import LineDeliveryResult, NotificationDelivery, NotificationIntent
from src.infrastructure.integrations.line_gateway import FakeLineDeliveryGateway


class FakeNotificationStore:
    def __init__(self) -> None:
        self.intents: dict[str, NotificationIntent] = {}
        self.deliveries: list[NotificationDelivery] = []
        self.next_intent_id = 1

    def create_intent(self, intent: NotificationIntent) -> NotificationIntent:
        saved = replace(intent, id=f"intent-{self.next_intent_id}")
        self.next_intent_id += 1
        self.intents[saved.id] = saved
        return saved

    def get_intent_for_user(self, user_id: str, intent_id: str | None) -> NotificationIntent | None:
        intent = self.intents.get(intent_id or "")
        if intent is None or intent.user_id != user_id:
            return None
        return intent

    def list_intents_for_user(self, user_id: str, *, limit: int | None = None, offset: int = 0) -> list[NotificationIntent]:
        values = [intent for intent in self.intents.values() if intent.user_id == user_id]
        return values[offset : offset + limit if limit is not None else None]

    def record_delivery(self, delivery: NotificationDelivery) -> NotificationDelivery:
        saved = replace(delivery, id=f"delivery-{len(self.deliveries) + 1}")
        self.deliveries.append(saved)
        return saved

    def list_deliveries_for_intent(
        self,
        notification_intent_id: str,
        *,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[NotificationDelivery]:
        values = [delivery for delivery in self.deliveries if delivery.notification_intent_id == notification_intent_id]
        return values[offset : offset + limit if limit is not None else None]

    def mark_intent_delivered(self, intent_id: str) -> NotificationIntent:
        return self._set_status(intent_id, "delivered")

    def mark_intent_retryable(self, intent_id: str) -> NotificationIntent:
        return self._set_status(intent_id, "retryable")

    def mark_intent_failed(self, intent_id: str) -> NotificationIntent:
        return self._set_status(intent_id, "failed")

    def _set_status(self, intent_id: str, status: str) -> NotificationIntent:
        updated = replace(self.intents[intent_id], status=status)
        self.intents[intent_id] = updated
        return updated


def test_recommendation_notification_intent_records_payload_without_delivery() -> None:
    store = FakeNotificationStore()
    gateway = FakeLineDeliveryGateway(LineDeliveryResult.success_response(provider_message_id="line-1"))
    handler = CreateRecommendationNotificationIntentHandler(notifications=store)

    intent = handler.handle(
        CreateRecommendationNotificationCommand(
            user_id="user-1",
            recommendation_id="rec-1",
            channel="line",
            title="Reduce tomorrow's workout",
            rationale="High fatigue trend",
            approval_url="https://johnny.example/recommendations/rec-1",
            evidence_url="https://johnny.example/recommendations/rec-1/evidence",
            scheduled_for=datetime(2027, 1, 1, 9, tzinfo=timezone.utc),
        )
    )

    assert intent.user_id == "user-1"
    assert intent.recommendation_id == "rec-1"
    assert intent.channel == "line"
    assert intent.scheduled_for == datetime(2027, 1, 1, 9, tzinfo=timezone.utc)
    assert intent.payload == {
        "message": "Johnny: Reduce tomorrow's workout\nHigh fatigue trend\nReview: https://johnny.example/recommendations/rec-1\nEvidence: https://johnny.example/recommendations/rec-1/evidence",
        "approval_url": "https://johnny.example/recommendations/rec-1",
        "evidence_url": "https://johnny.example/recommendations/rec-1/evidence",
    }
    assert gateway.delivered_intents == []


def test_recommendation_notification_creation_avoids_duplicate_active_intents() -> None:
    store = FakeNotificationStore()
    handler = CreateRecommendationNotificationIntentHandler(notifications=store)
    command = CreateRecommendationNotificationCommand(
        user_id="user-1",
        recommendation_id="rec-1",
        channel="line",
        title="Review recommendation",
        rationale="Fatigue is elevated",
        approval_url="https://johnny.example/recommendations/rec-1",
        evidence_url="https://johnny.example/recommendations/rec-1/evidence",
    )

    first = handler.handle(command)
    second = handler.handle(command)

    assert first.id == second.id
    assert len(store.intents) == 1


def test_line_payload_formatter_keeps_concise_body_and_links() -> None:
    payload = format_line_recommendation_payload(
        title="Reduce tomorrow's workout because the title is intentionally longer than the channel needs",
        rationale="High fatigue trend from recent HRV and sleep data.",
        approval_url="https://johnny.example/recommendations/rec-1",
        evidence_url="https://johnny.example/recommendations/rec-1/evidence",
    )

    assert payload["approval_url"] == "https://johnny.example/recommendations/rec-1"
    assert payload["evidence_url"] == "https://johnny.example/recommendations/rec-1/evidence"
    assert len(payload["message"]) <= 240
    assert "Evidence: https://johnny.example/recommendations/rec-1/evidence" in payload["message"]


def test_notification_delivery_success_records_attempt_and_marks_delivered() -> None:
    store = FakeNotificationStore()
    intent = store.create_intent(_intent())
    gateway = FakeLineDeliveryGateway(LineDeliveryResult.success_response(provider_message_id="line-message-1"))
    handler = NotificationDeliveryHandler(notifications=store, gateway=gateway)

    delivered = handler.handle(DeliverNotificationCommand(user_id="user-1", intent_id=intent.id))

    assert delivered.status == "delivered"
    assert len(store.deliveries) == 1
    assert store.deliveries[0].provider_message_id == "line-message-1"
    assert gateway.delivered_intents == [intent]


def test_notification_delivery_failure_records_retryable_attempt_and_retry_preserves_intent() -> None:
    store = FakeNotificationStore()
    intent = store.create_intent(_intent())
    gateway = FakeLineDeliveryGateway(LineDeliveryResult.failure(status_code=500, response={"error": "temporary"}))
    handler = NotificationDeliveryHandler(notifications=store, gateway=gateway)

    retryable = handler.handle(DeliverNotificationCommand(user_id="user-1", intent_id=intent.id))
    retryable_again = handler.handle(DeliverNotificationCommand(user_id="user-1", intent_id=intent.id))

    assert retryable.status == "retryable"
    assert retryable_again.id == intent.id
    assert retryable_again.status == "retryable"
    assert len(store.deliveries) == 2


def test_notification_delivery_terminal_failure_after_max_attempts() -> None:
    store = FakeNotificationStore()
    intent = store.create_intent(_intent())
    gateway = FakeLineDeliveryGateway(LineDeliveryResult.failure(status_code=400, response={"error": "bad request"}))
    handler = NotificationDeliveryHandler(notifications=store, gateway=gateway, max_attempts=1)

    failed = handler.handle(DeliverNotificationCommand(user_id="user-1", intent_id=intent.id))

    assert failed.status == "failed"
    assert store.deliveries[0].response["retryable"] is False


def _intent() -> NotificationIntent:
    return NotificationIntent.recommendation(
        user_id="user-1",
        recommendation_id="rec-1",
        channel="line",
        payload={"message": "Johnny: Review recommendation", "approval_url": "https://johnny.example/recommendations/rec-1"},
    )
