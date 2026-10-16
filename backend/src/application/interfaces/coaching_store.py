from __future__ import annotations

from datetime import date, datetime
from typing import Protocol

from src.domain.training_plan import Workout
from src.domain.training_review import PrescriptionSnapshot


class CoachingStore(Protocol):
    def list_prescriptions(
        self, user_id: str, starts_on: date, ends_on: date,
        timezone_name: str, activity_starts: dict[str, datetime],
    ) -> tuple[PrescriptionSnapshot, ...]: ...

    def record_plan_activation(
        self, *, user_id: str, plan_id: str, effective_at: datetime,
        effective_local_date: date, timezone_name: str, previous_plan_id: str | None,
    ) -> str: ...

    def record_prescription_revision(
        self, *, user_id: str, plan_id: str, workout: Workout, effective_at: datetime,
        source: str, confidence: str, recommendation_id: str | None,
    ) -> str: ...
