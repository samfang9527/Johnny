from __future__ import annotations

from datetime import date, datetime
from typing import Literal

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
    body_battery_score: float | None = Field(default=None, ge=0)


class DailyHealthMetricsResponse(BaseModel):
    user_id: str
    metric_date: date
    source: str
    values: dict[str, float]


class DetailCoverageResponse(BaseModel):
    state: Literal['complete', 'partial', 'unknown']
    sampling: Literal['recorded', 'chart', 'unknown']
    covered_seconds: float | None = None
    missing_channels: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class ActivitySegmentSummaryResponse(BaseModel):
    source_index: int
    source_kind: str
    start_at: datetime | None = None
    end_at: datetime | None = None
    timer_seconds: float | None = None
    elapsed_seconds: float | None = None
    distance_meters: float | None = None
    average_heart_rate_bpm: float | None = None
    average_pace_seconds_per_km: float | None = None
    step_path: str | None = None


class UsedActivityDetailResponse(BaseModel):
    snapshot_id: str
    activity_id: str
    resource: str
    coverage: DetailCoverageResponse
    precision: Literal['recorded', 'sampled', 'unknown']
    segments: list[ActivitySegmentSummaryResponse]


class ActivityDetailStatusResponse(BaseModel):
    activity_id: str
    resource: str
    status: str
    current_snapshot_id: str | None = None
    coverage: DetailCoverageResponse | None = None


class ExecutionFactResponse(BaseModel):
    id: str
    metric: str
    value: float
    unit: str
    scope: str
    evidence_refs: list[str]
    denominator_seconds: float | None = None
    covered_seconds: float | None = None


class ExecutionFindingResponse(BaseModel):
    code: str
    fact_ids: list[str]
    supports: str
    does_not_support: str


class ExecutionAnalysisResponse(BaseModel):
    activity_id: str
    activity_ids: list[str]
    fingerprint: str
    prescription_revision_id: str | None = None
    snapshot_ids: list[str]
    mapping: Literal['exact', 'estimated', 'unmatched']
    facts: list[ExecutionFactResponse]
    findings: list[ExecutionFindingResponse]
    limitations: list[str]
    algorithm_version: str


class ActivityExecutionResponse(BaseModel):
    activity_id: str
    analysis_id: str | None = None
    freshness: Literal['current', 'stale', 'unavailable']
    analysis: ExecutionAnalysisResponse | None = None
    used_details: list[UsedActivityDetailResponse] = Field(default_factory=list)
    current_details: list[ActivityDetailStatusResponse] = Field(default_factory=list)


class ActivityDetailCoverageSummaryResponse(BaseModel):
    total_activities: int
    with_details: int
    without_details: int
    fetch_status_counts: dict[str, int]
    coverage_state_counts: dict[str, int]
    sampling_counts: dict[str, int]
