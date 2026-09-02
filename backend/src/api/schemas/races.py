from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict, Field


class RaceGoalCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    race_date: date
    distance_meters: int = Field(gt=0)
    target_finish_seconds: int | None = Field(default=None, gt=0)
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
    priority: str
    status: str
    target_pace_seconds_per_km: float | None = None
