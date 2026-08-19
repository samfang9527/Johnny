from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.domain.training_analytics import TrainingMetricSnapshot

from .models import TrainingMetricSnapshotModel


class SqlAlchemyTrainingMetricSnapshotRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def save_snapshot(self, user_id: str, snapshot: TrainingMetricSnapshot) -> TrainingMetricSnapshot:
        _ensure_matching_user_id(user_id, snapshot.user_id)
        model = TrainingMetricSnapshotModel(
            user_id=user_id,
            snapshot_type=snapshot.snapshot_type,
            captured_at=snapshot.captured_at,
            metrics=snapshot.metrics,
        )
        self._session.add(model)
        self._session.flush()
        return _snapshot_from_model(model)

    def get_snapshot_for_user(self, user_id: str, snapshot_id: str | None) -> TrainingMetricSnapshot | None:
        if snapshot_id is None:
            return None
        model = self._session.scalar(
            select(TrainingMetricSnapshotModel).where(
                TrainingMetricSnapshotModel.id == snapshot_id,
                TrainingMetricSnapshotModel.user_id == user_id,
            )
        )
        if model is None:
            return None
        return _snapshot_from_model(model)

    def list_snapshots_for_user(
        self,
        user_id: str,
        *,
        snapshot_type: str | None = None,
        captured_at_from: datetime | None = None,
        captured_at_to: datetime | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[TrainingMetricSnapshot]:
        statement = select(TrainingMetricSnapshotModel).where(TrainingMetricSnapshotModel.user_id == user_id)
        if snapshot_type is not None:
            statement = statement.where(TrainingMetricSnapshotModel.snapshot_type == snapshot_type)
        if captured_at_from is not None:
            statement = statement.where(TrainingMetricSnapshotModel.captured_at >= captured_at_from)
        if captured_at_to is not None:
            statement = statement.where(TrainingMetricSnapshotModel.captured_at <= captured_at_to)
        statement = statement.order_by(TrainingMetricSnapshotModel.captured_at.desc(), TrainingMetricSnapshotModel.id.desc())
        if offset:
            statement = statement.offset(offset)
        if limit is not None:
            statement = statement.limit(limit)
        return [_snapshot_from_model(model) for model in self._session.scalars(statement)]


def _ensure_matching_user_id(trusted_user_id: str, payload_user_id: str) -> None:
    if trusted_user_id != payload_user_id:
        raise ValueError("payload user_id does not match repository user_id")


def _snapshot_from_model(model: TrainingMetricSnapshotModel) -> TrainingMetricSnapshot:
    return TrainingMetricSnapshot.create(
        id=model.id,
        user_id=model.user_id,
        snapshot_type=model.snapshot_type,
        captured_at=model.captured_at,
        metrics=model.metrics or {},
    )
