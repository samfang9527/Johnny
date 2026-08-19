from __future__ import annotations

from datetime import date
from typing import Protocol


class UserRepository(Protocol):
    def create_user(self, *, email: str, display_name: str) -> object:
        ...

    def get(self, user_id: str) -> object | None:
        ...


class TrainingPlanRepository(Protocol):
    def create_plan(
        self,
        *,
        user_id: str,
        race_id: str | None,
        name: str,
        starts_on: date,
        ends_on: date,
    ) -> object:
        ...

    def get_current_plan_for_user(self, user_id: str) -> object | None:
        ...


class RecommendationRepository(Protocol):
    def create_recommendation(self, *, user_id: str, title: str, rationale: str, evidence: dict | None = None) -> object:
        ...

    def record_decision(self, recommendation_id: str, *, decision: str) -> object:
        ...
