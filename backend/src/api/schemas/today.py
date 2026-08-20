from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel


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
