"""Review activity grouping and matching without modifying canonical workouts."""
from datetime import date, datetime, timedelta, timezone
from uuid import uuid4
from zoneinfo import ZoneInfo

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlalchemy import select

from src.api.dependencies import CurrentUserDependency, SessionDependency
from src.api.errors import ApiConflictError, ApiNotFoundError
from src.api.schemas.common import DataEnvelope
from src.api.routes.agent_runs import _queue_handler
from src.application.training_analytics import resolve_plan_for_date
from src.application.daily_advice_sync import recovery_data_limited
from src.domain.integrations_notifications import SyncSummary
from src.domain.daily_advice import RefreshVersion
from src.infrastructure.database.daily_advice_repository import SqlAlchemyDailyAdviceRepository
from src.infrastructure.database.models import DailyAdviceModel, SyncRunModel, IntegrationConnectionModel
from src.infrastructure.database.session_review_repository import SqlAlchemySessionReviewRepository, SessionReviewConflict, REVIEW_WINDOW_DAYS, session_payload

router = APIRouter(prefix='/activities/session-reviews', tags=['activities'])


class ReviewGroup(BaseModel):
    activity_ids: list[str] = Field(min_length=1, max_length=100)
    workout_id: str | None = None


class ReviewDecision(BaseModel):
    activity_ids: list[str] = Field(min_length=1, max_length=100)
    groups: list[ReviewGroup] = Field(min_length=1, max_length=100)


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
        day = repository.save_decisions(current_user.id, payload.activity_ids, [g.model_dump() for g in payload.groups])
    except LookupError as error:
        raise ApiNotFoundError(str(error)) from error
    except SessionReviewConflict as error:
        raise ApiConflictError(str(error)) from error
    now = datetime.now(timezone.utc)
    today = now.astimezone(ZoneInfo(repository.timezone_for(current_user.id))).date()
    affected = set(session.scalars(select(DailyAdviceModel.advice_date).where(
        DailyAdviceModel.user_id == current_user.id,
        DailyAdviceModel.week_start <= day, DailyAdviceModel.week_end >= day,
        DailyAdviceModel.advice_date >= day,
    )))
    affected.add(today)
    advice = SqlAlchemyDailyAdviceRepository(session)
    queue = _queue_handler(session, daily_advice=True)
    runs = []
    for anchor in sorted(affected):
        if resolve_plan_for_date(repository.plans, current_user.id, anchor) is None:
            continue
        previous = advice.get_for_user_date(current_user.id, anchor)
        source_sync = previous.source_sync_run_id if previous else None
        sync = session.scalar(select(SyncRunModel).join(IntegrationConnectionModel,
            IntegrationConnectionModel.id == SyncRunModel.integration_connection_id).where(
            SyncRunModel.id == source_sync, IntegrationConnectionModel.user_id == current_user.id)) if source_sync else None
        limited_recovery = sync is None or recovery_data_limited(SyncSummary.from_payload(sync.summary))
        result = queue.queue_run(user_id=current_user.id, workflow_name='daily_recommendation', trigger_type='manual',
            idempotency_key=f'session-review:{current_user.id}:{anchor}:{uuid4()}',
            payload={'anchor_date': anchor.isoformat(), 'source_sync_run_id': source_sync,
                     'limited_recovery': limited_recovery,
                     'refresh_observed_at': now.isoformat()})
        advice.begin_refresh(current_user.id, anchor, RefreshVersion(now, result.run.id), source_sync)
        runs.append({'run_id': result.run.id, 'poll_url': result.poll_url, 'anchor_date': anchor.isoformat()})
    return DataEnvelope(data={'saved': True, 'refresh_runs': runs})
