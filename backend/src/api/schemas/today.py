from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel


class PlanWeekResponse(BaseModel):
    starts_on: date
    ends_on: date


class WorkoutGuideResponse(BaseModel):
    purpose: str
    expected_feel: str
    if_too_hard: str
    if_too_easy: str


class DailyAdviceResponse(BaseModel):
    id: str
    advice_date: date
    state: str
    data_freshness: str
    generated_at: datetime | None = None
    source_sync_run_id: str | None = None
    source_run_id: str | None = None
    plan_version_id: str | None = None
    workout_id: str | None = None
    execution_mode: str | None = None
    plan_week: PlanWeekResponse | None = None
    facts: dict[str, Any] | None = None
    week_summary: str | None = None
    today_execution: str | None = None
    workout_guide: WorkoutGuideResponse | None = None


class TodayContextResponse(BaseModel):
    user_id: str
    anchor_date: date
    scheduled_workouts: list[dict[str, Any]]
    recent_activities: list[dict[str, Any]]
    training_load: dict[str, Any]
    recovery: dict[str, Any]
    unavailable_signals: list[str]
    next_race: dict[str, Any] | None = None
    current_recommendation: dict[str, Any] | None = None
    daily_advice: DailyAdviceResponse | None = None
