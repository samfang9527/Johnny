from __future__ import annotations

from datetime import date, timedelta
from typing import Protocol

from src.application.interfaces.training_analytics_repository import TrainingAnalyticsReadRepository
from src.domain.training_analytics import (
    RecoveryService,
    TodayContext,
    TrainingLoadService,
)
from src.domain.training_plan import TrainingPlan


class CurrentTrainingPlanRepository(Protocol):
    def get_current_plan_for_user(self, user_id: str) -> TrainingPlan | None:
        ...


class TodayContextService:
    def __init__(
        self,
        *,
        activity_repository: TrainingAnalyticsReadRepository,
        training_plan_repository: CurrentTrainingPlanRepository,
        training_load_service: TrainingLoadService | None = None,
        recovery_service: RecoveryService | None = None,
    ) -> None:
        self._activity_repository = activity_repository
        self._training_plan_repository = training_plan_repository
        self._training_load_service = training_load_service or TrainingLoadService()
        self._recovery_service = recovery_service or RecoveryService()

    def build(self, *, user_id: str, anchor_date: date) -> TodayContext:
        history_start = anchor_date - timedelta(days=27)
        recent_start = anchor_date - timedelta(days=6)
        activities = tuple(
            self._activity_repository.list_activities_for_user_between(
                user_id,
                history_start,
                anchor_date,
            )
        )
        health_metrics = tuple(
            self._activity_repository.list_daily_health_metrics_for_user_between(
                user_id,
                history_start,
                anchor_date,
            )
        )
        plan = self._training_plan_repository.get_current_plan_for_user(user_id)
        if plan is not None and plan.user_id != user_id:
            plan = None

        training_load = self._training_load_service.calculate(
            user_id=user_id,
            anchor_date=anchor_date,
            activities=activities,
        )
        recovery = self._recovery_service.calculate(
            user_id=user_id,
            anchor_date=anchor_date,
            health_metrics=health_metrics,
            training_load=training_load,
        )

        return TodayContext(
            user_id=user_id,
            anchor_date=anchor_date,
            scheduled_workouts=tuple(
                workout.to_payload()
                for workout in (plan.workouts if plan is not None else ())
                if workout.scheduled_for == anchor_date
            ),
            recent_activities=tuple(
                _activity_summary(activity)
                for activity in activities
                if activity.user_id == user_id and recent_start <= activity.started_at.date() <= anchor_date
            ),
            training_load=training_load,
            recovery=recovery,
            unavailable_signals=tuple(
                dict.fromkeys((*training_load.unavailable_signals, *recovery.unavailable_signals))
            ),
        )


def _activity_summary(activity) -> dict:
    return {
        "id": activity.id,
        "user_id": activity.user_id,
        "source": activity.source,
        "started_at": activity.started_at.isoformat(),
        "sport_type": activity.sport_type,
        "distance_meters": activity.distance_meters,
        "duration_seconds": activity.duration_seconds,
        "average_pace_seconds_per_km": activity.average_pace_seconds_per_km,
        "average_heart_rate": activity.average_heart_rate,
        "matched_workout_id": activity.matched_workout_id,
    }
