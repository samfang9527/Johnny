from __future__ import annotations

from datetime import date
from typing import Protocol

from src.domain.activity_health import CompletedActivity, DailyHealthMetrics


class ActivityRepository(Protocol):
    def save_activity(self, user_id: str, activity: CompletedActivity) -> CompletedActivity | None:
        ...

    def get_activity_for_user(self, user_id: str, activity_id: str | None) -> CompletedActivity | None:
        ...

    def list_activities_for_user(self, user_id: str) -> list[CompletedActivity]:
        ...

    def save_daily_health_metrics(self, user_id: str, metrics: DailyHealthMetrics) -> DailyHealthMetrics:
        ...

    def get_daily_health_metrics_for_user(self, user_id: str, metric_date: date) -> DailyHealthMetrics | None:
        ...
