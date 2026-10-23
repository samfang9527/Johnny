from __future__ import annotations

from datetime import date

from fastapi import APIRouter

from src.api.dependencies import CurrentUserDependency, SessionDependency
from src.api.schemas.common import DataEnvelope
from src.api.schemas.today import TodayContextResponse
from src.application.training_analytics import BuildTodayContextHandler
from src.domain.daily_advice import DailyAdvice
from src.infrastructure.database.activity_repository import SqlAlchemyActivityRepository
from src.infrastructure.database.athlete_race_repository import SqlAlchemyAthleteRaceRepository
from src.infrastructure.database.daily_advice_repository import SqlAlchemyDailyAdviceRepository
from src.infrastructure.database.coaching_repository import SqlAlchemyCoachingRepository
from src.infrastructure.database.models import WorkoutAdviceModel
from sqlalchemy import select
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
    advice = SqlAlchemyDailyAdviceRepository(session).get_for_user_date(current_user.id, anchor_date)
    payload["daily_advice"] = _daily_advice_payload(advice) if advice is not None else None
    latest = session.scalar(select(WorkoutAdviceModel).where(
        WorkoutAdviceModel.user_id == current_user.id,
        WorkoutAdviceModel.advice_date == anchor_date,
        WorkoutAdviceModel.current_revision_id.is_not(None),
    ).order_by(WorkoutAdviceModel.updated_at.desc(), WorkoutAdviceModel.id.desc()).limit(1))
    workout_advice = (SqlAlchemyCoachingRepository(session).get_advice_slot(
        current_user.id, latest.advice_date, latest.slot_key) if latest else None)
    payload["workout_advice"] = workout_advice
    payload["workout_advice_summary"] = _workout_advice_summary(workout_advice)
    return DataEnvelope(data=TodayContextResponse(**payload))


def _workout_advice_summary(slot: dict | None) -> dict | None:
    if slot is None or not isinstance(slot.get('current'), dict):
        return None
    current = slot['current']
    guidance = current.get('guidance')
    result = {'advice_id': slot['id'], 'advice_date': slot['advice_date'],
              'freshness': slot['freshness'],
              'guidance': guidance if isinstance(guidance, str) else ''}
    analysis = current.get('analysis')
    if isinstance(analysis, dict) and analysis.get('analysis_mode') in {'llm', 'rules'}:
        result.update({'headline': analysis.get('headline'),
                       'summary': analysis.get('summary'),
                       'analysis_mode': analysis['analysis_mode']})
    return result


def _daily_advice_payload(advice: DailyAdvice) -> dict:
    return {
        "id": advice.id,
        "advice_date": advice.advice_date,
        "state": advice.state,
        "data_freshness": advice.data_freshness,
        "generated_at": advice.generated_at,
        "source_sync_run_id": advice.source_sync_run_id,
        "source_run_id": advice.source_run_id,
        "plan_version_id": advice.plan_version_id,
        "workout_id": advice.workout_id,
        "execution_mode": advice.execution_mode,
        "plan_week": (
            {"starts_on": advice.week_start, "ends_on": advice.week_end}
            if advice.week_start is not None and advice.week_end is not None else None
        ),
        "facts": advice.facts.to_payload() if advice.facts is not None else None,
        "week_summary": advice.sections.week_summary if advice.sections is not None else None,
        "today_execution": advice.sections.today_execution if advice.sections is not None else None,
        "workout_guide": advice.sections.workout_guide.to_payload() if advice.sections is not None else None,
    }


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
