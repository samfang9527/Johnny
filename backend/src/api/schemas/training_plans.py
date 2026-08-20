from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field


class WorkoutRequest(BaseModel):
    scheduled_for: date
    workout_type: str
    purpose: str
    planned_duration_minutes: int | None = Field(default=None, gt=0)
    planned_distance_meters: int | None = Field(default=None, gt=0)
    pace_range_seconds_per_km: list[int] | None = None
    heart_rate_zone: str | None = None
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
    status: str


class TrainingPlanRequest(BaseModel):
    race_id: str | None = None
    name: str = Field(min_length=1)
    starts_on: date
    ends_on: date
    status: str = "active"
    workouts: list[WorkoutRequest] = Field(default_factory=list)


class TrainingPlanResponse(BaseModel):
    id: str | None
    user_id: str
    race_id: str | None
    name: str
    status: str
    starts_on: date
    ends_on: date
    workouts: list[WorkoutResponse]
