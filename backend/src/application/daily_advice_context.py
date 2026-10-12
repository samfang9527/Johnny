"""Load activity evidence for a training plan's own seven-day block."""

from __future__ import annotations

from datetime import date, datetime, timedelta

from src.application.interfaces.training_analytics_store import TrainingAnalyticsDataProvider
from src.domain.daily_advice import WeekExecution, build_week_execution, plan_week_for_date
from src.domain.training_plan import TrainingPlan
from src.application.training_analytics import resolve_plan_for_date


def load_week_execution(
    *,
    training_data: TrainingAnalyticsDataProvider,
    plan: TrainingPlan,
    user_id: str,
    anchor_date: date,
    as_of: datetime,
    timezone_name: str,
    activity_coverage_complete: bool,
) -> WeekExecution:
    if plan.user_id != user_id:
        raise ValueError("training plan does not belong to user")
    week_start, week_end = plan_week_for_date(plan, anchor_date)
    activities = tuple(training_data.list_activities_for_user_between(
        user_id, week_start - timedelta(days=1), week_end + timedelta(days=1),
    ))
    return build_week_execution(
        plan, activities, anchor_date=anchor_date, as_of=as_of,
        timezone_name=timezone_name, activity_coverage_complete=activity_coverage_complete,
    )
