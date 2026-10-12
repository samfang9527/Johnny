from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field


class DailyRecommendationRunRequest(BaseModel):
    anchor_date: date | None = None
    force: bool = False


class TrainingPlanGenerationRunRequest(BaseModel):
    race_id: str | None = None
    starts_on: date | None = None
    ends_on: date | None = None
    plan_horizon_weeks: int | None = Field(default=None, ge=1, le=16)
    goal_notes: str | None = None
    plan_type: str = "race"


class QueuedAgentRunResponse(BaseModel):
    run_id: str
    status: str
    workflow_name: str
    poll_url: str


class AgentRunResponse(BaseModel):
    id: str | None
    user_id: str
    status: str
    trigger_type: str
    workflow_name: str
    prompt_version: str
    provider: str | None = None
    model: str | None = None
    correlation_id: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    latency_ms: int | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    input_summary: str | None = None
    output_summary: str | None = None
    error_type: str | None = None
    error_message: str | None = None
    recommendation_id: str | None = None
    daily_advice_id: str | None = None


class AgentRunStepResponse(BaseModel):
    id: str | None
    agent_run_id: str
    sequence_number: int
    step_type: str
    name: str
    status: str
    tool_name: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    latency_ms: int | None = None
    input_summary: str | None = None
    output_summary: str | None = None
    error_type: str | None = None
    error_message: str | None = None
    payload: dict[str, Any]
