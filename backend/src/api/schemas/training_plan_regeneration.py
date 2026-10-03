from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field


class TrainingPlanRegenerationRequest(BaseModel):
    client_request_id: str = Field(min_length=1, max_length=120)
    race_id: str | None = None
    plan_type: Literal["race", "maintenance"] = "race"


class RegenerationQuotaResponse(BaseModel):
    quota_day: date
    limit: int
    used: int
    remaining: int
    available: bool
    next_available_at: datetime | None = None


class RegenerationStrategyResponse(BaseModel):
    race_id: str | None
    plan_type: Literal["race", "maintenance"]
    reason: str
    starts_on: date
    plan_horizon_weeks: int


class RegenerationRunResponse(BaseModel):
    run_id: str
    status: str
    workflow_name: str
    poll_url: str


class TrainingPlanRegenerationResponse(BaseModel):
    quota: RegenerationQuotaResponse
    default_strategy: RegenerationStrategyResponse
    in_flight_run: RegenerationRunResponse | None = None
    run: RegenerationRunResponse | None = None
