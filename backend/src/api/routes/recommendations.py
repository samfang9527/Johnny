from __future__ import annotations

from fastapi import APIRouter

from src.api.dependencies import CurrentUserDependency, SessionDependency, ensure_current_user
from src.api.errors import ApiNotFoundError
from src.api.schemas.common import DEFAULT_PAGE_LIMIT, DataEnvelope, ListEnvelope, PageLimit, PageOffset, list_envelope, page_query_limit
from src.api.schemas.conversations import ConversationMessageResponse
from src.api.schemas.recommendations import DiscussRecommendationRequest, RecommendationRequest, RecommendationResponse
from src.application.conversations import SubmitConversationMessageHandler
from src.application.recommendation_approval import AcceptRecommendationHandler, EditRecommendationHandler, RejectRecommendationHandler
from src.domain.recommendation_approval import EvidenceItem, ProposedAction, Recommendation
from src.infrastructure.database.recommendation_repository import SqlAlchemyRecommendationRepository
from src.infrastructure.database.training_plan_repository import SqlAlchemyTrainingPlanRepository


router = APIRouter(prefix="/recommendations", tags=["recommendations"])


@router.post("", response_model=DataEnvelope[RecommendationResponse])
def create_recommendation(
    payload: RecommendationRequest,
    current_user: CurrentUserDependency,
    session: SessionDependency,
) -> DataEnvelope[RecommendationResponse]:
    ensure_current_user(session, current_user)
    recommendation = Recommendation.create(
        user_id=current_user.id,
        recommendation_type=payload.recommendation_type,
        priority=payload.priority,
        title=payload.title,
        rationale=payload.rationale,
        evidence=tuple(EvidenceItem.from_payload(item.model_dump()) for item in payload.evidence),
        proposed_action=ProposedAction.from_payload(payload.proposed_action),
        training_plan_id=payload.training_plan_id,
        workout_id=payload.workout_id,
    )
    saved = SqlAlchemyRecommendationRepository(session).create_recommendation(current_user.id, recommendation)
    return DataEnvelope(data=_recommendation_response(saved))


@router.get("", response_model=ListEnvelope[RecommendationResponse])
def list_recommendations(
    current_user: CurrentUserDependency,
    session: SessionDependency,
    limit: PageLimit = DEFAULT_PAGE_LIMIT,
    offset: PageOffset = 0,
) -> ListEnvelope[RecommendationResponse]:
    recommendations = SqlAlchemyRecommendationRepository(session).list_recommendations_for_user(
        current_user.id,
        limit=page_query_limit(limit),
        offset=offset,
    )
    return list_envelope([_recommendation_response(recommendation) for recommendation in recommendations], limit=limit, offset=offset)


@router.post("/{recommendation_id}/accept", response_model=DataEnvelope[RecommendationResponse])
def accept_recommendation(
    recommendation_id: str,
    current_user: CurrentUserDependency,
    session: SessionDependency,
) -> DataEnvelope[RecommendationResponse]:
    result = AcceptRecommendationHandler(
        recommendations=SqlAlchemyRecommendationRepository(session),
        training_plans=SqlAlchemyTrainingPlanRepository(session),
    ).handle(user_id=current_user.id, recommendation_id=recommendation_id)
    if result is None:
        raise ApiNotFoundError("recommendation not found")
    return DataEnvelope(data=_recommendation_response(result))


@router.post("/{recommendation_id}/reject", response_model=DataEnvelope[RecommendationResponse])
def reject_recommendation(
    recommendation_id: str,
    current_user: CurrentUserDependency,
    session: SessionDependency,
) -> DataEnvelope[RecommendationResponse]:
    result = RejectRecommendationHandler(recommendations=SqlAlchemyRecommendationRepository(session)).handle(
        user_id=current_user.id,
        recommendation_id=recommendation_id,
    )
    if result is None:
        raise ApiNotFoundError("recommendation not found")
    return DataEnvelope(data=_recommendation_response(result))


@router.post("/{recommendation_id}/edit", response_model=DataEnvelope[RecommendationResponse])
def edit_recommendation(
    recommendation_id: str,
    payload: dict,
    current_user: CurrentUserDependency,
    session: SessionDependency,
) -> DataEnvelope[RecommendationResponse]:
    result = EditRecommendationHandler(recommendations=SqlAlchemyRecommendationRepository(session)).handle(
        user_id=current_user.id,
        recommendation_id=recommendation_id,
        revised_action=ProposedAction.from_payload(payload),
    )
    if result is None:
        raise ApiNotFoundError("recommendation not found")
    return DataEnvelope(data=_recommendation_response(result))


@router.post("/{recommendation_id}/discuss", response_model=DataEnvelope[ConversationMessageResponse])
def discuss_recommendation(
    recommendation_id: str,
    payload: DiscussRecommendationRequest,
    current_user: CurrentUserDependency,
) -> DataEnvelope[ConversationMessageResponse]:
    message = SubmitConversationMessageHandler().handle(
        user_id=current_user.id,
        recommendation_id=recommendation_id,
        content=payload.content,
    )
    return DataEnvelope(
        data=ConversationMessageResponse(
            message={"user_id": message.user_id, "content": message.content, "recommendation_id": message.recommendation_id},
            run_ref=message.run_ref or "",
        )
    )


def _recommendation_response(recommendation: Recommendation) -> RecommendationResponse:
    payload = recommendation.to_payload()
    return RecommendationResponse(
        id=recommendation.id,
        user_id=recommendation.user_id,
        recommendation_type=recommendation.recommendation_type,
        priority=recommendation.priority,
        title=recommendation.title,
        rationale=recommendation.rationale,
        status=recommendation.status,
        decision=recommendation.decision,
        training_plan_id=recommendation.training_plan_id,
        workout_id=recommendation.workout_id,
        evidence=payload["evidence"]["items"],
        proposed_action=payload["proposed_action"],
    )
