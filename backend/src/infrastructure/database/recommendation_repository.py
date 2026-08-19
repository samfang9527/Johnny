from __future__ import annotations

from sqlalchemy.orm import Session

from .models import RecommendationModel, utc_now


class SqlAlchemyRecommendationRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create_recommendation(
        self,
        *,
        user_id: str,
        title: str,
        rationale: str,
        evidence: dict | None = None,
        training_plan_id: str | None = None,
    ) -> RecommendationModel:
        recommendation = RecommendationModel(
            user_id=user_id,
            training_plan_id=training_plan_id,
            title=title,
            rationale=rationale,
            evidence=evidence or {},
        )
        self._session.add(recommendation)
        self._session.flush()
        return recommendation

    def get(self, recommendation_id: str) -> RecommendationModel | None:
        return self._session.get(RecommendationModel, recommendation_id)

    def record_decision(self, recommendation_id: str, *, decision: str) -> RecommendationModel:
        recommendation = self._session.get(RecommendationModel, recommendation_id)
        if recommendation is None:
            raise ValueError(f"Recommendation not found: {recommendation_id}")
        recommendation.decision = decision
        recommendation.decision_at = utc_now()
        recommendation.status = "decided"
        self._session.flush()
        return recommendation
