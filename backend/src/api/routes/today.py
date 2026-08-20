from __future__ import annotations

from datetime import date

from fastapi import APIRouter

from src.api.dependencies import CurrentUserDependency, SessionDependency
from src.api.schemas.common import DataEnvelope
from src.api.schemas.today import TodayContextResponse
from src.application.training_analytics import BuildTodayContextHandler
from src.infrastructure.database.activity_repository import SqlAlchemyActivityRepository
from src.infrastructure.database.athlete_race_repository import SqlAlchemyAthleteRaceRepository
from src.infrastructure.database.recommendation_repository import SqlAlchemyRecommendationRepository
from src.infrastructure.database.training_plan_repository import SqlAlchemyTrainingPlanRepository


router = APIRouter(prefix="/today", tags=["today"])


@router.get("", response_model=DataEnvelope[TodayContextResponse])
def get_today(
    current_user: CurrentUserDependency,
    session: SessionDependency,
    anchor_date: date,
) -> DataEnvelope[TodayContextResponse]:
    handler = BuildTodayContextHandler(
        training_data=SqlAlchemyActivityRepository(session),
        training_plans=SqlAlchemyTrainingPlanRepository(session),
    )
    payload = handler.handle(user_id=current_user.id, anchor_date=anchor_date).to_payload()
    payload["next_race"] = _next_race_payload(session, current_user.id, anchor_date)
    payload["current_recommendation"] = _current_recommendation_payload(session, current_user.id)
    return DataEnvelope(data=TodayContextResponse(**payload))


def _next_race_payload(session, user_id: str, anchor_date: date) -> dict | None:  # noqa: ANN001
    races = SqlAlchemyAthleteRaceRepository(session).list_race_goals_for_user(
        user_id,
        race_date_from=anchor_date,
        limit=1,
        offset=0,
    )
    if not races:
        return None
    race = races[0]
    return {
        "id": race.id,
        "name": race.name,
        "race_date": race.race_date.isoformat(),
        "distance_meters": race.distance_meters,
        "priority": race.priority,
        "status": race.status,
    }


def _current_recommendation_payload(session, user_id: str) -> dict | None:  # noqa: ANN001
    recommendations = SqlAlchemyRecommendationRepository(session).list_recommendations_for_user(
        user_id,
        limit=1,
        offset=0,
    )
    if not recommendations:
        return None
    recommendation = recommendations[0]
    return {
        "id": recommendation.id,
        "title": recommendation.title,
        "rationale": recommendation.rationale,
        "status": recommendation.status,
        "decision": recommendation.decision,
        "priority": recommendation.priority,
    }
