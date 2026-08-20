from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class EvidenceItemSchema(BaseModel):
    source: str
    metric: str
    value: Any
    unit: str | None = None
    observed_at: str | None = None
    summary: str | None = None


class RecommendationRequest(BaseModel):
    recommendation_type: str
    priority: str
    title: str = Field(min_length=1)
    rationale: str = Field(min_length=1)
    evidence: list[EvidenceItemSchema]
    proposed_action: dict[str, Any]
    training_plan_id: str | None = None
    workout_id: str | None = None


class RecommendationResponse(BaseModel):
    id: str | None
    user_id: str
    recommendation_type: str
    priority: str
    title: str
    rationale: str
    status: str
    decision: str | None
    training_plan_id: str | None
    workout_id: str | None
    evidence: list[dict[str, Any]]
    proposed_action: dict[str, Any]


class DiscussRecommendationRequest(BaseModel):
    content: str = Field(min_length=1)
