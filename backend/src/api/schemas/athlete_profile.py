from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class AthleteProfileRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    timezone: str = Field(min_length=1)
    experience_level: Literal["beginner", "intermediate", "advanced"] | None = None
    current_weekly_mileage_km: float = Field(ge=0)
    preferred_training_days: list[str]
    preferred_long_run_day: str
    max_runs_per_week: int = Field(ge=1, le=7)
    max_hard_sessions_per_week: int = Field(default=2, ge=0, le=2)
    unit_preference: Literal["metric", "imperial"] = "metric"
    threshold_pace_seconds_per_km: int | None = Field(default=None, ge=120, le=900)
    resting_heart_rate_bpm: int | None = Field(default=None, gt=0)
    max_heart_rate_bpm: int | None = Field(default=None, gt=0)
    training_preferences: dict = Field(default_factory=dict)
    injury_status: Literal["none", "current", "recent", "recurring"] = "none"
    injury_areas: list[Literal["knee", "calf", "shin", "ankle", "foot", "hamstring", "quad", "hip", "back", "other"]] = Field(
        default_factory=list
    )
    injury_notes: str | None = None

    @model_validator(mode="after")
    def validate_injury_notes(self) -> AthleteProfileRequest:
        if "other" in self.injury_areas and not (self.injury_notes or "").strip():
            raise ValueError("other injury area requires injury notes")
        if (
            self.resting_heart_rate_bpm is not None
            and self.max_heart_rate_bpm is not None
            and self.max_heart_rate_bpm <= self.resting_heart_rate_bpm
        ):
            raise ValueError("maximum heart rate must exceed resting heart rate")
        return self


class AthleteProfileResponse(AthleteProfileRequest):
    garmin_training_evidence: dict = Field(default_factory=dict)
    id: str | None
    user_id: str
