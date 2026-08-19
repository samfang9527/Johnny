from __future__ import annotations

from datetime import date, datetime
from typing import Protocol

from src.domain.activity_health import CompletedActivity, DailyHealthMetrics
from src.domain.training_analytics import TrainingMetricSnapshot


class TrainingAnalyticsReadRepository(Protocol):
    def list_activities_for_user_between(
        self,
        user_id: str,
        started_on_or_after: date,
        started_on_or_before: date,
        *,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[CompletedActivity]:
        ...

    def list_daily_health_metrics_for_user_between(
        self,
        user_id: str,
        measured_on_or_after: date,
        measured_on_or_before: date,
        *,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[DailyHealthMetrics]:
        ...


class TrainingMetricSnapshotRepository(Protocol):
    def save_snapshot(self, user_id: str, snapshot: TrainingMetricSnapshot) -> TrainingMetricSnapshot:
        ...

    def get_snapshot_for_user(self, user_id: str, snapshot_id: str | None) -> TrainingMetricSnapshot | None:
        ...

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
        ...
