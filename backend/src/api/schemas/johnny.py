from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class WorkoutAdviceConstraintsRequest(BaseModel):
    available_minutes: int | None = Field(default=None, ge=1, le=600)
    feeling: Literal["usual", "more_tired"] = "usual"
    cannot_train_today: bool = False

    @model_validator(mode="after")
    def validate_combination(self):
        if self.cannot_train_today and self.available_minutes is not None:
            raise ValueError("cannot_train_today cannot be combined with available_minutes")
        return self


class WorkoutAdviceRequest(BaseModel):
    client_request_id: UUID
    workout_id: UUID | None = None
    constraints: WorkoutAdviceConstraintsRequest = Field(default_factory=WorkoutAdviceConstraintsRequest)


class RetryReviewRequest(BaseModel):
    source: Literal['stored_evidence', 'sync'] = 'stored_evidence'
