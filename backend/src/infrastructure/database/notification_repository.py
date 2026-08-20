from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.domain.integrations_notifications import NotificationDelivery, NotificationIntent

from .models import NotificationDeliveryModel, NotificationIntentModel


class SqlAlchemyNotificationRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create_intent(self, intent: NotificationIntent) -> NotificationIntent:
        model = NotificationIntentModel(
            user_id=intent.user_id,
            recommendation_id=intent.recommendation_id,
            channel=intent.channel,
            status=intent.status,
            scheduled_for=intent.scheduled_for,
            payload=intent.payload,
        )
        self._session.add(model)
        self._session.flush()
        return _intent_from_model(model)

    def get_intent_for_user(self, user_id: str, intent_id: str | None) -> NotificationIntent | None:
        if intent_id is None:
            return None
        model = self._session.scalar(
            select(NotificationIntentModel).where(
                NotificationIntentModel.id == intent_id,
                NotificationIntentModel.user_id == user_id,
            )
        )
        if model is None:
            return None
        return _intent_from_model(model)

    def list_intents_for_user(
        self,
        user_id: str,
        *,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[NotificationIntent]:
        statement = (
            select(NotificationIntentModel)
            .where(NotificationIntentModel.user_id == user_id)
            .order_by(NotificationIntentModel.created_at.desc(), NotificationIntentModel.id.desc())
        )
        if offset:
            statement = statement.offset(offset)
        if limit is not None:
            statement = statement.limit(limit)
        return [_intent_from_model(model) for model in self._session.scalars(statement)]

    def record_delivery(self, delivery: NotificationDelivery) -> NotificationDelivery:
        model = NotificationDeliveryModel(
            notification_intent_id=delivery.notification_intent_id,
            status=delivery.status,
            provider=delivery.provider,
            provider_message_id=delivery.provider_message_id,
            attempted_at=delivery.attempted_at,
            response=delivery.response,
        )
        self._session.add(model)
        self._session.flush()
        return _delivery_from_model(model)

    def list_deliveries_for_intent(
        self,
        notification_intent_id: str,
        *,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[NotificationDelivery]:
        statement = (
            select(NotificationDeliveryModel)
            .where(NotificationDeliveryModel.notification_intent_id == notification_intent_id)
            .order_by(NotificationDeliveryModel.attempted_at, NotificationDeliveryModel.id)
        )
        if offset:
            statement = statement.offset(offset)
        if limit is not None:
            statement = statement.limit(limit)
        return [_delivery_from_model(model) for model in self._session.scalars(statement)]

    def mark_intent_delivered(self, intent_id: str) -> NotificationIntent:
        return self._set_intent_status(intent_id, "delivered")

    def mark_intent_retryable(self, intent_id: str) -> NotificationIntent:
        return self._set_intent_status(intent_id, "retryable")

    def mark_intent_failed(self, intent_id: str) -> NotificationIntent:
        return self._set_intent_status(intent_id, "failed")

    def _set_intent_status(self, intent_id: str, status: str) -> NotificationIntent:
        model = self._session.get(NotificationIntentModel, intent_id)
        if model is None:
            raise ValueError(f"Notification intent not found: {intent_id}")
        model.status = status
        self._session.flush()
        return _intent_from_model(model)


def _intent_from_model(model: NotificationIntentModel) -> NotificationIntent:
    return NotificationIntent(
        id=model.id,
        user_id=model.user_id,
        recommendation_id=model.recommendation_id,
        channel=model.channel,
        status=model.status,
        scheduled_for=model.scheduled_for,
        payload=model.payload or {},
    )


def _delivery_from_model(model: NotificationDeliveryModel) -> NotificationDelivery:
    return NotificationDelivery(
        id=model.id,
        notification_intent_id=model.notification_intent_id,
        status=model.status,
        provider=model.provider or "line",
        provider_message_id=model.provider_message_id,
        attempted_at=model.attempted_at,
        response=model.response or {},
    )
