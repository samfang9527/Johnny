from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class RaceGoalCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    race_date: date
    distance_meters: int = Field(gt=0)
    target_finish_seconds: int | None = Field(default=None, gt=0)
    ascent_meters: float | None = Field(default=None, ge=0)
    descent_meters: float | None = Field(default=None, ge=0)
    terrain_difficulty: Literal["runnable", "mixed", "technical"] | None = None
    cutoff_seconds: int | None = Field(default=None, gt=0)
    goal_intent: Literal["complete", "perform"] | None = None
    priority: str = "primary"


class RaceGoalUpdateRequest(RaceGoalCreateRequest):
    model_config = ConfigDict(extra="forbid")

    status: str = "planned"


class RaceGoalResponse(BaseModel):
    id: str | None
    user_id: str
    name: str
    race_date: date
    distance_meters: int
    target_finish_seconds: int | None = None
    ascent_meters: float | None = None
    descent_meters: float | None = None
    terrain_difficulty: Literal["runnable", "mixed", "technical"] | None = None
    cutoff_seconds: int | None = None
    goal_intent: Literal["complete", "perform"] | None = None
    priority: str
    status: str
    target_pace_seconds_per_km: float | None = None
