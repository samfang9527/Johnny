from __future__ import annotations

from pydantic import BaseModel, Field


class AthleteProfileRequest(BaseModel):
    timezone: str = Field(min_length=1)
    experience_level: str
    current_weekly_mileage: float = Field(ge=0)
    preferred_training_days: list[str]
    preferred_long_run_day: str
    max_runs_per_week: int = Field(ge=1, le=7)
    unit_preference: str = "metric"
    training_preferences: dict = Field(default_factory=dict)
    injury_notes: str | None = None


class AthleteProfileResponse(AthleteProfileRequest):
    id: str | None
    user_id: str
