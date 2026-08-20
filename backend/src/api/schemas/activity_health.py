from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field


class ActivityRequest(BaseModel):
    source: str = "manual"
    started_at: datetime
    sport_type: str
    distance_meters: float = Field(gt=0)
    duration_seconds: int = Field(gt=0)
    average_pace_seconds_per_km: float | None = Field(default=None, gt=0)
    source_activity_id: str | None = None
    provider_connection_id: str | None = None
    average_heart_rate: float | None = Field(default=None, gt=0)
    elevation_gain_meters: float | None = None


class ActivityResponse(BaseModel):
    id: str | None
    user_id: str
    source: str
    started_at: datetime
    sport_type: str
    distance_meters: float
    duration_seconds: int
    average_pace_seconds_per_km: float
    source_activity_id: str | None = None
    provider_connection_id: str | None = None
    average_heart_rate: float | None = None
    elevation_gain_meters: float | None = None


class DailyHealthMetricsRequest(BaseModel):
    metric_date: date
    source: str = "manual"
    sleep_duration_minutes: float | None = Field(default=None, ge=0)
    sleep_quality: float | None = Field(default=None, ge=0)
    hrv_ms: float | None = Field(default=None, ge=0)
    hrv_baseline_ms: float | None = Field(default=None, ge=0)
    resting_heart_rate: float | None = Field(default=None, ge=0)
    stress_score: float | None = Field(default=None, ge=0)


class DailyHealthMetricsResponse(BaseModel):
    user_id: str
    metric_date: date
    source: str
    values: dict[str, float]
