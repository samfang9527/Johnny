from __future__ import annotations

from datetime import date

from fastapi import APIRouter

from src.api.dependencies import CurrentUserDependency, SessionDependency, ensure_current_user
from src.api.schemas.activity_health import (
    ActivityRequest,
    ActivityResponse,
    DailyHealthMetricsRequest,
    DailyHealthMetricsResponse,
)
from src.api.schemas.common import DEFAULT_PAGE_LIMIT, DataEnvelope, ListEnvelope, PageLimit, PageOffset, list_envelope, page_query_limit
from src.domain.activity_health import CompletedActivity, DailyHealthMetrics
from src.infrastructure.database.activity_repository import SqlAlchemyActivityRepository


activity_router = APIRouter(prefix="/activities", tags=["activities"])
health_router = APIRouter(prefix="/health-metrics", tags=["health-metrics"])


@activity_router.post("", response_model=DataEnvelope[ActivityResponse])
def create_activity(
    payload: ActivityRequest,
    current_user: CurrentUserDependency,
    session: SessionDependency,
) -> DataEnvelope[ActivityResponse]:
    ensure_current_user(session, current_user)
    activity = CompletedActivity.create(user_id=current_user.id, **payload.model_dump())
    saved = SqlAlchemyActivityRepository(session).save_activity(current_user.id, activity)
    return DataEnvelope(data=_activity_response(saved or activity))


@activity_router.get("", response_model=ListEnvelope[ActivityResponse])
def list_activities(
    current_user: CurrentUserDependency,
    session: SessionDependency,
    started_on_or_after: date | None = None,
    started_on_or_before: date | None = None,
    limit: PageLimit = DEFAULT_PAGE_LIMIT,
    offset: PageOffset = 0,
) -> ListEnvelope[ActivityResponse]:
    repository = SqlAlchemyActivityRepository(session)
    if started_on_or_after is not None and started_on_or_before is not None:
        activities = repository.list_activities_for_user_between(
            current_user.id,
            started_on_or_after,
            started_on_or_before,
            limit=page_query_limit(limit),
            offset=offset,
        )
    else:
        activities = repository.list_activities_for_user(current_user.id, limit=page_query_limit(limit), offset=offset)
    return list_envelope([_activity_response(activity) for activity in activities], limit=limit, offset=offset)


@health_router.post("/daily", response_model=DataEnvelope[DailyHealthMetricsResponse])
def save_daily_health_metrics(
    payload: DailyHealthMetricsRequest,
    current_user: CurrentUserDependency,
    session: SessionDependency,
) -> DataEnvelope[DailyHealthMetricsResponse]:
    ensure_current_user(session, current_user)
    metrics = DailyHealthMetrics.create(user_id=current_user.id, **payload.model_dump())
    saved = SqlAlchemyActivityRepository(session).save_daily_health_metrics(current_user.id, metrics)
    return DataEnvelope(data=_health_response(saved))


@health_router.get("/daily", response_model=ListEnvelope[DailyHealthMetricsResponse])
def list_daily_health_metrics(
    current_user: CurrentUserDependency,
    session: SessionDependency,
    measured_on_or_after: date,
    measured_on_or_before: date,
    limit: PageLimit = DEFAULT_PAGE_LIMIT,
    offset: PageOffset = 0,
) -> ListEnvelope[DailyHealthMetricsResponse]:
    metrics = SqlAlchemyActivityRepository(session).list_daily_health_metrics_for_user_between(
        current_user.id,
        measured_on_or_after,
        measured_on_or_before,
        limit=page_query_limit(limit),
        offset=offset,
    )
    return list_envelope([_health_response(metric) for metric in metrics], limit=limit, offset=offset)


def _activity_response(activity: CompletedActivity) -> ActivityResponse:
    return ActivityResponse(
        id=activity.id,
        user_id=activity.user_id,
        source=activity.source,
        started_at=activity.started_at,
        sport_type=activity.sport_type,
        distance_meters=activity.distance_meters,
        duration_seconds=activity.duration_seconds,
        average_pace_seconds_per_km=activity.average_pace_seconds_per_km,
        source_activity_id=activity.source_activity_id,
        provider_connection_id=activity.provider_connection_id,
        average_heart_rate=activity.average_heart_rate,
        elevation_gain_meters=activity.elevation_gain_meters,
    )


def _health_response(metrics: DailyHealthMetrics) -> DailyHealthMetricsResponse:
    return DailyHealthMetricsResponse(
        user_id=metrics.user_id,
        metric_date=metrics.metric_date,
        source=metrics.source,
        values=metrics.values_by_metric_type(),
    )
