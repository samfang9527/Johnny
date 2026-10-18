"""Review activity grouping and matching without modifying canonical workouts."""
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter
from pydantic import BaseModel, Field

from src.api.dependencies import CurrentUserDependency, SessionDependency
from src.api.errors import ApiConflictError, ApiNotFoundError
from src.api.schemas.common import DataEnvelope
from src.application.coaching_refresh import CoachingRefreshService
from src.infrastructure.database.session_review_repository import SqlAlchemySessionReviewRepository, SessionReviewConflict, REVIEW_WINDOW_DAYS, session_payload

router = APIRouter(prefix='/activities/session-reviews', tags=['activities'])


class ReviewGroup(BaseModel):
    activity_ids: list[str] = Field(min_length=1, max_length=100)
    workout_id: str | None = None


class ReviewDecision(BaseModel):
    activity_ids: list[str] = Field(min_length=1, max_length=100)
    groups: list[ReviewGroup] = Field(min_length=1, max_length=100)


class SwapDecision(BaseModel):
    activity_ids: list[str] = Field(min_length=1, max_length=100)
    workout_id: str


@router.get('')
def list_reviews(current_user: CurrentUserDependency, session: SessionDependency, anchor_date: date):
    repository = SqlAlchemySessionReviewRepository(session)
    first_day, today = repository.review_window(current_user.id)
    start = max(first_day, anchor_date-timedelta(days=REVIEW_WINDOW_DAYS-1))
    end = min(today, anchor_date)
    if start > end:
        return DataEnvelope(data=[])
    return DataEnvelope(data=[session_payload(s) for s in repository.list_sessions(current_user.id, start, end)])


@router.post('')
def save_reviews(payload: ReviewDecision, current_user: CurrentUserDependency, session: SessionDependency):
    repository = SqlAlchemySessionReviewRepository(session)
    try:
        changed_dates = repository.save_decisions(current_user.id, payload.activity_ids, [g.model_dump() for g in payload.groups])
    except LookupError as error:
        raise ApiNotFoundError(str(error)) from error
    except SessionReviewConflict as error:
        raise ApiConflictError(str(error)) from error
    return _refresh_after_pairing(repository, current_user.id, session, changed_dates)


@router.post('/swap')
def swap_reviews(payload: SwapDecision, current_user: CurrentUserDependency, session: SessionDependency):
    repository = SqlAlchemySessionReviewRepository(session)
    try:
        changed_dates = repository.swap_decisions(current_user.id, payload.activity_ids, payload.workout_id)
    except LookupError as error:
        raise ApiNotFoundError(str(error)) from error
    except SessionReviewConflict as error:
        raise ApiConflictError(str(error)) from error
    return _refresh_after_pairing(repository, current_user.id, session, changed_dates)


def _refresh_after_pairing(repository, user_id: str, session, changed_dates: set[date]):
    today = datetime.now(timezone.utc).astimezone(ZoneInfo(repository.timezone_for(user_id))).date()
    effects = CoachingRefreshService(session).record_change(
        user_id=user_id, changed_dates=changed_dates, today=today,
        reason='activity_pairing_changed', affects_advice=True,
    )
    return DataEnvelope(data={'saved': True, 'refresh_runs': [
        {'run_id': run_id, 'poll_url': f'/api/v1/agent-runs/{run_id}'}
        for run_id in effects.review_run_ids],
        'advice_invalidated': bool(effects.invalidated_advice_ids)})
