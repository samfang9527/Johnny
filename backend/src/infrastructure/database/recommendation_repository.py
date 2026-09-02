from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.domain.recommendation_approval import Recommendation

from .models import RecommendationModel, utc_now


class SqlAlchemyRecommendationRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create_recommendation(
        self,
        user_id: str | None = None,
        recommendation: Recommendation | None = None,
        *,
        title: str | None = None,
        rationale: str | None = None,
        evidence: dict | None = None,
        training_plan_id: str | None = None,
    ) -> RecommendationModel | Recommendation:
        if recommendation is not None:
            if user_id is None:
                user_id = recommendation.user_id
            _ensure_matching_user_id(user_id, recommendation.user_id)
            model = RecommendationModel(
                user_id=user_id,
                training_plan_id=recommendation.training_plan_id,
                title=recommendation.title,
                rationale=recommendation.rationale,
                status=recommendation.status,
                decision=recommendation.decision,
                decision_at=utc_now() if recommendation.decision is not None else None,
                evidence=recommendation.to_evidence_payload(),
            )
            self._session.add(model)
            self._session.flush()
            return _recommendation_from_model(model)

        if user_id is None or title is None or rationale is None:
            raise ValueError("user_id, title, and rationale are required")
        model = RecommendationModel(
            user_id=user_id,
            training_plan_id=training_plan_id,
            title=title,
            rationale=rationale,
            evidence=evidence or {},
        )
        self._session.add(model)
        self._session.flush()
        return model

    def get(self, recommendation_id: str) -> RecommendationModel | None:
        return self._session.get(RecommendationModel, recommendation_id)

    def get_recommendation_for_user(self, user_id: str, recommendation_id: str | None) -> Recommendation | None:
        if recommendation_id is None:
            return None
        model = self._session.scalar(
            select(RecommendationModel).where(
                RecommendationModel.id == recommendation_id,
                RecommendationModel.user_id == user_id,
            )
        )
        if model is None:
            return None
        return _recommendation_from_model(model)

    def save_recommendation(self, user_id: str, recommendation: Recommendation) -> Recommendation | None:
        _ensure_matching_user_id(user_id, recommendation.user_id)
        if recommendation.id is None:
            return self.create_recommendation(user_id, recommendation)
        model = self._session.scalar(
            select(RecommendationModel).where(
                RecommendationModel.id == recommendation.id,
                RecommendationModel.user_id == user_id,
            )
        )
        if model is None:
            return None
        model.training_plan_id = recommendation.training_plan_id
        model.title = recommendation.title
        model.rationale = recommendation.rationale
        model.status = recommendation.status
        model.decision = recommendation.decision
        if recommendation.decision is not None and model.decision_at is None:
            model.decision_at = utc_now()
        model.evidence = recommendation.to_evidence_payload()
        self._session.flush()
        return _recommendation_from_model(model)

    def list_recommendations_for_user(
        self,
        user_id: str,
        *,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[Recommendation]:
        statement = (
            select(RecommendationModel)
            .where(RecommendationModel.user_id == user_id)
            .order_by(RecommendationModel.created_at.desc(), RecommendationModel.id.desc())
        )
        if offset:
            statement = statement.offset(offset)
        if limit is not None:
            statement = statement.limit(limit)
        return [_recommendation_from_model(model) for model in self._session.scalars(statement)]

    def record_decision(self, recommendation_id: str, *, decision: str) -> RecommendationModel:
        recommendation = self._session.get(RecommendationModel, recommendation_id)
        if recommendation is None:
            raise ValueError(f"Recommendation not found: {recommendation_id}")
        recommendation.decision = decision
        recommendation.decision_at = utc_now()
        recommendation.status = "decided"
        self._session.flush()
        return recommendation


def _ensure_matching_user_id(trusted_user_id: str, payload_user_id: str) -> None:
    if trusted_user_id != payload_user_id:
        raise ValueError("payload user_id does not match repository user_id")


def _recommendation_from_model(model: RecommendationModel) -> Recommendation:
    return Recommendation.from_payload(
        id=model.id,
        user_id=model.user_id,
        title=model.title,
        rationale=model.rationale,
        status=model.status,
        decision=model.decision,
        evidence_payload=model.evidence or {},
        training_plan_id=model.training_plan_id,
        created_at=model.created_at,
    )
