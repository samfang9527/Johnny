from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class WorkoutTargetPayload(BaseModel):
    kind: Literal["pace", "heart_rate", "rpe"]
    zone: Literal["easy", "steady", "marathon", "threshold", "interval", "repetition", "rpe_only"] | None = None
    heart_rate_zone: str | None = None
    rpe: int | None = Field(default=None, ge=1, le=10)
    pace_range_seconds_per_km: list[int] | None = None
    heart_rate_range_bpm: list[int] | None = None
    confidence: Literal["high", "medium", "low"] | None = None


class WorkoutStepPayload(BaseModel):
    type: Literal["warmup", "work", "recovery", "cooldown", "repeat", "drill", "stride", "hill", "free_run"]
    duration_seconds: int | None = Field(default=None, gt=0)
    distance_meters: int | None = Field(default=None, gt=0)
    target: WorkoutTargetPayload | None = None
    repeat_count: int | None = Field(default=None, ge=1)
    steps: list["WorkoutStepPayload"] = Field(default_factory=list)
    notes: str | None = None
    grade_notes: str | None = None

    @model_validator(mode="after")
    def validate_step_load(self) -> "WorkoutStepPayload":
        if self.type == "repeat":
            if self.repeat_count is None:
                raise ValueError("repeat block requires positive repeat count")
            if not self.steps:
                raise ValueError("repeat block requires nested steps")
            return self
        if self.duration_seconds is None and self.distance_meters is None:
            raise ValueError("step requires distance or duration")
        return self


class WorkoutRequest(BaseModel):
    scheduled_for: date
    workout_type: str
    purpose: str
    planned_duration_minutes: int | None = Field(default=None, gt=0)
    planned_distance_meters: int | None = Field(default=None, gt=0)
    pace_range_seconds_per_km: list[int] | None = None
    heart_rate_zone: str | None = None
    phase: str | None = None
    coach_note: str | None = Field(default=None, max_length=500)
    steps: list[WorkoutStepPayload] = Field(default_factory=list)
    status: str = "planned"


class WorkoutStatusRequest(BaseModel):
    status: str


class WorkoutResponse(BaseModel):
    id: str | None
    scheduled_for: date
    workout_type: str
    purpose: str
    planned_duration_minutes: int | None = None
    planned_distance_meters: int | None = None
    pace_range_seconds_per_km: list[int] | None = None
    heart_rate_zone: str | None = None
    phase: str | None = None
    coach_note: str | None = None
    steps: list[dict[str, Any]] = Field(default_factory=list)
    compact_summary: str | None = None
    status: str


class TrainingPlanRequest(BaseModel):
    race_id: str | None = None
    name: str = Field(min_length=1)
    starts_on: date
    ends_on: date
    status: str = "active"
    metadata: dict[str, Any] = Field(default_factory=dict)
    workouts: list[WorkoutRequest] = Field(default_factory=list)


class TrainingPlanResponse(BaseModel):
    id: str | None
    user_id: str
    race_id: str | None
    name: str
    status: str
    starts_on: date
    ends_on: date
    metadata: dict[str, Any] = Field(default_factory=dict)
    workouts: list[WorkoutResponse]
