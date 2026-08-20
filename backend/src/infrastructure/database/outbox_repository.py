from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.domain.integrations_notifications import OutboxEvent

from .models import OutboxEventModel


class SqlAlchemyOutboxRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create_event(self, event: OutboxEvent) -> OutboxEvent:
        model = OutboxEventModel(
            topic=event.topic,
            payload=event.payload,
            status=event.status,
            published_at=event.published_at,
        )
        self._session.add(model)
        self._session.flush()
        return _event_from_model(model)

    def list_pending_events(self, *, limit: int | None = None, offset: int = 0) -> list[OutboxEvent]:
        statement = select(OutboxEventModel).where(OutboxEventModel.status == "pending").order_by(OutboxEventModel.created_at, OutboxEventModel.id)
        if offset:
            statement = statement.offset(offset)
        if limit is not None:
            statement = statement.limit(limit)
        return [_event_from_model(model) for model in self._session.scalars(statement)]


def _event_from_model(model: OutboxEventModel) -> OutboxEvent:
    return OutboxEvent(
        id=model.id,
        topic=model.topic,
        payload=model.payload or {},
        status=model.status,
        published_at=model.published_at,
    )
