from __future__ import annotations

from typing import Protocol

from src.domain.recommendation_approval import Recommendation


class RecommendationStore(Protocol):
    def create_recommendation(self, user_id: str, recommendation: Recommendation) -> Recommendation:
        ...

    def save_recommendation(self, user_id: str, recommendation: Recommendation) -> Recommendation | None:
        ...

    def get_recommendation_for_user(self, user_id: str, recommendation_id: str | None) -> Recommendation | None:
        ...

    def list_recommendations_for_user(
        self,
        user_id: str,
        *,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[Recommendation]:
        ...
