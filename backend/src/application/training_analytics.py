from __future__ import annotations

from datetime import date, timedelta

from src.application.interfaces.training_analytics_store import TrainingAnalyticsDataProvider
from src.application.interfaces.training_plan_store import TrainingPlanStore
from src.domain.training_analytics import (
    RecoveryService,
    TodayContext,
    TrainingLoadService,
)
from src.domain.training_plan import TrainingPlan


class BuildTodayContextHandler:
    def __init__(
        self,
        *,
        training_data: TrainingAnalyticsDataProvider,
        training_plans: TrainingPlanStore,
        training_load_service: TrainingLoadService | None = None,
        recovery_service: RecoveryService | None = None,
    ) -> None:
        self._training_data = training_data
        self._training_plans = training_plans
        self._training_load_service = training_load_service or TrainingLoadService()
        self._recovery_service = recovery_service or RecoveryService()

    def handle(self, *, user_id: str, anchor_date: date) -> TodayContext:
        history_start = anchor_date - timedelta(days=27)
        recent_start = anchor_date - timedelta(days=6)
        activities = tuple(
            self._training_data.list_activities_for_user_between(
                user_id,
                history_start,
                anchor_date,
            )
        )
        health_metrics = tuple(
            self._training_data.list_daily_health_metrics_for_user_between(
                user_id,
                history_start,
                anchor_date,
            )
        )
        plan = resolve_plan_for_date(self._training_plans, user_id, anchor_date)

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


def resolve_plan_for_date(plans: TrainingPlanStore, user_id: str, anchor_date: date) -> TrainingPlan | None:
    plan = plans.get_current_plan_for_user(user_id)
    visited: set[str | None] = set()
    # A newly projected plan starts tomorrow; predecessor workouts can still own today.
    while plan is not None and plan.user_id == user_id and anchor_date < plan.starts_on:
        if plan.id in visited:
            return None
        visited.add(plan.id)
        plan = plans.get_plan_for_user(user_id, plan.metadata.get("previous_plan_id"))
        if plan is not None and plan.status not in {"active", "superseded", "completed"}:
            return None
    if plan is None or plan.user_id != user_id or not plan.starts_on <= anchor_date <= plan.ends_on:
        return None
    return plan
