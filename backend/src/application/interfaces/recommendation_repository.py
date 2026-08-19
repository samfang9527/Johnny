from __future__ import annotations

from typing import Protocol


class RecommendationRepository(Protocol):
    def create_recommendation(self, *, user_id: str, title: str, rationale: str, evidence: dict | None = None) -> object:
        ...

    def record_decision(self, recommendation_id: str, *, decision: str) -> object:
        ...
