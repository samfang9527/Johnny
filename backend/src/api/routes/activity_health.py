from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter
from sqlalchemy import func, select

from src.api.dependencies import CurrentUserDependency, SessionDependency, ensure_current_user
from src.api.errors import ApiNotFoundError
from src.api.schemas.activity_health import (
    ActivityRequest,
    ActivityResponse,
    ActivityDetailCoverageSummaryResponse,
    ActivityDetailStatusResponse,
    ActivityExecutionResponse,
    ActivitySegmentSummaryResponse,
    DetailCoverageResponse,
    DailyHealthMetricsRequest,
    DailyHealthMetricsResponse,
    ExecutionAnalysisResponse,
    UsedActivityDetailResponse,
)
from src.api.schemas.common import DEFAULT_PAGE_LIMIT, DataEnvelope, ListEnvelope, PageLimit, PageOffset, list_envelope, page_query_limit
from src.application.coaching_refresh import CoachingRefreshService
from src.domain.activity_health import CompletedActivity, DailyHealthMetrics
from src.infrastructure.database.activity_repository import SqlAlchemyActivityRepository
from src.infrastructure.database.athlete_race_repository import SqlAlchemyAthleteRaceRepository
from src.infrastructure.database.models import (
    ActivityDetailFetchModel, ActivityDetailSnapshotModel, ActivityExecutionAnalysisModel,
    ActivityModel, ActivitySegmentModel,
)


activity_router = APIRouter(prefix="/activities", tags=["activities"])
health_router = APIRouter(prefix="/health-metrics", tags=["health-metrics"])


def _current_snapshot(fetch, snapshots: dict[str, ActivityDetailSnapshotModel]):
    snapshot = snapshots.get(fetch.current_snapshot_id)
    if (snapshot is None or snapshot.activity_id != fetch.activity_id
            or snapshot.resource != fetch.resource):
        return None
    return snapshot


@activity_router.post("", response_model=DataEnvelope[ActivityResponse])
def create_activity(
    payload: ActivityRequest,
    current_user: CurrentUserDependency,
    session: SessionDependency,
) -> DataEnvelope[ActivityResponse]:
    ensure_current_user(session, current_user)
    activity = CompletedActivity.create(user_id=current_user.id, **payload.model_dump())
    saved = SqlAlchemyActivityRepository(session).save_activity(current_user.id, activity)
    if saved is not None:
        timezone_name = _timezone_name(session, current_user.id)
        zone = ZoneInfo(timezone_name)
        CoachingRefreshService(session).record_change(
            user_id=current_user.id, changed_dates={activity.started_at.astimezone(zone).date()},
            today=datetime.now(timezone.utc).astimezone(zone).date(),
            reason='activity_created',
        )
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


@activity_router.get('/detail-coverage', response_model=DataEnvelope[ActivityDetailCoverageSummaryResponse])
def get_activity_detail_coverage(
    current_user: CurrentUserDependency,
    session: SessionDependency,
) -> DataEnvelope[ActivityDetailCoverageSummaryResponse]:
    total = session.scalar(select(func.count(ActivityModel.id)).where(
        ActivityModel.user_id == current_user.id)) or 0
    fetches = session.scalars(select(ActivityDetailFetchModel).join(
        ActivityModel, ActivityDetailFetchModel.activity_id == ActivityModel.id).where(
        ActivityDetailFetchModel.user_id == current_user.id,
        ActivityModel.user_id == current_user.id)).all()
    status_counts = Counter(row.status for row in fetches)
    current_ids = {row.current_snapshot_id for row in fetches if row.current_snapshot_id}
    snapshots = session.scalars(select(ActivityDetailSnapshotModel).where(
        ActivityDetailSnapshotModel.user_id == current_user.id,
        ActivityDetailSnapshotModel.id.in_(current_ids))).all() if current_ids else ()
    snapshot_map = {row.id: row for row in snapshots}
    current_snapshots = [_current_snapshot(row, snapshot_map) for row in fetches]
    with_details = {fetch.activity_id for fetch, snapshot in zip(fetches, current_snapshots)
                    if snapshot is not None}
    coverage_counts = Counter((row.coverage or {}).get('state', 'unknown')
                              for row in current_snapshots if row is not None)
    sampling_counts = Counter((row.coverage or {}).get('sampling', 'unknown')
                              for row in current_snapshots if row is not None)
    return DataEnvelope(data=ActivityDetailCoverageSummaryResponse(
        total_activities=total, with_details=len(with_details),
        without_details=total - len(with_details),
        fetch_status_counts=dict(status_counts), coverage_state_counts=dict(coverage_counts),
        sampling_counts=dict(sampling_counts)))


@activity_router.get('/{activity_id}/execution', response_model=DataEnvelope[ActivityExecutionResponse])
def get_activity_execution(
    activity_id: str,
    current_user: CurrentUserDependency,
    session: SessionDependency,
    analysis_id: str | None = None,
) -> DataEnvelope[ActivityExecutionResponse]:
    owned = session.scalar(select(ActivityModel.id).where(
        ActivityModel.id == activity_id, ActivityModel.user_id == current_user.id))
    if owned is None:
        raise ApiNotFoundError('activity not found')
    latest = session.scalar(select(ActivityExecutionAnalysisModel).where(
        ActivityExecutionAnalysisModel.user_id == current_user.id,
        ActivityExecutionAnalysisModel.activity_id == activity_id).order_by(
            ActivityExecutionAnalysisModel.created_at.desc(),
            ActivityExecutionAnalysisModel.id.desc()).limit(1))
    selected = latest if analysis_id is None else session.scalar(select(
        ActivityExecutionAnalysisModel).where(
            ActivityExecutionAnalysisModel.id == analysis_id,
            ActivityExecutionAnalysisModel.user_id == current_user.id,
            ActivityExecutionAnalysisModel.activity_id == activity_id))
    if analysis_id is not None and selected is None:
        raise ApiNotFoundError('analysis not found')
    activity_ids = tuple((selected.payload or {}).get('activity_ids') or (activity_id,)) if selected else (activity_id,)
    if not activity_ids or activity_ids[0] != activity_id:
        raise ApiNotFoundError('analysis not found')
    visible_ids = set(session.scalars(select(ActivityModel.id).where(
        ActivityModel.user_id == current_user.id,
        ActivityModel.id.in_(activity_ids))).all())
    if visible_ids != set(activity_ids):
        raise ApiNotFoundError('analysis not found')
    fetches = session.scalars(select(ActivityDetailFetchModel).join(
        ActivityModel, ActivityDetailFetchModel.activity_id == ActivityModel.id).where(
        ActivityDetailFetchModel.user_id == current_user.id,
        ActivityModel.user_id == current_user.id,
        ActivityDetailFetchModel.activity_id.in_(activity_ids)).order_by(
            ActivityDetailFetchModel.activity_id, ActivityDetailFetchModel.resource)).all()
    current_ids = {row.current_snapshot_id for row in fetches if row.current_snapshot_id}
    selected_ids = tuple(selected.snapshot_ids or ()) if selected else ()
    snapshot_ids = current_ids | set(selected_ids)
    snapshots = {row.id: row for row in session.scalars(select(ActivityDetailSnapshotModel).where(
        ActivityDetailSnapshotModel.user_id == current_user.id,
        ActivityDetailSnapshotModel.activity_id.in_(activity_ids),
        ActivityDetailSnapshotModel.id.in_(snapshot_ids))).all()} if snapshot_ids else {}
    current_snapshots = [_current_snapshot(row, snapshots) for row in fetches]
    current_details = [ActivityDetailStatusResponse(
        activity_id=row.activity_id, resource=row.resource, status=row.status,
        current_snapshot_id=snapshot.id if snapshot else None,
        coverage=DetailCoverageResponse.model_validate(snapshot.coverage) if snapshot else None)
        for row, snapshot in zip(fetches, current_snapshots)]
    current_ids = {snapshot.id for snapshot in current_snapshots if snapshot is not None}
    used_details = []
    for snapshot_id in selected_ids:
        snapshot = snapshots.get(snapshot_id)
        if snapshot is None:
            continue
        coverage = DetailCoverageResponse.model_validate(snapshot.coverage)
        segments = session.scalars(select(ActivitySegmentModel).where(
            ActivitySegmentModel.user_id == current_user.id,
            ActivitySegmentModel.snapshot_id == snapshot_id).order_by(
                ActivitySegmentModel.ordinal)).all()
        used_details.append(UsedActivityDetailResponse(
            snapshot_id=snapshot.id, activity_id=snapshot.activity_id,
            resource=snapshot.resource, coverage=coverage,
            precision=('sampled' if coverage.sampling == 'chart' else coverage.sampling),
            segments=[ActivitySegmentSummaryResponse.model_validate(row.payload)
                      for row in segments]))
    freshness = ('unavailable' if selected is None else
                 'current' if latest is not None and selected.id == latest.id
                 and set(selected_ids) == current_ids and len(used_details) == len(selected_ids)
                 else 'stale')
    return DataEnvelope(data=ActivityExecutionResponse(
        activity_id=activity_id, analysis_id=selected.id if selected else None,
        freshness=freshness,
        analysis=(ExecutionAnalysisResponse.model_validate({**selected.payload,
            'activity_ids': list(activity_ids), 'snapshot_ids': list(selected_ids)})
                  if selected else None),
        used_details=used_details, current_details=current_details))


@health_router.post("/daily", response_model=DataEnvelope[DailyHealthMetricsResponse])
def save_daily_health_metrics(
    payload: DailyHealthMetricsRequest,
    current_user: CurrentUserDependency,
    session: SessionDependency,
) -> DataEnvelope[DailyHealthMetricsResponse]:
    ensure_current_user(session, current_user)
    metrics = DailyHealthMetrics.create(user_id=current_user.id, **payload.model_dump())
    repository = SqlAlchemyActivityRepository(session)
    previous = repository.get_daily_health_metrics_for_user(current_user.id, metrics.metric_date)
    saved = repository.save_daily_health_metrics(current_user.id, metrics)
    if previous is None or previous.values_by_metric_type() != saved.values_by_metric_type():
        zone = ZoneInfo(_timezone_name(session, current_user.id))
        CoachingRefreshService(session).record_change(
            user_id=current_user.id, changed_dates={metrics.metric_date},
            today=datetime.now(timezone.utc).astimezone(zone).date(),
            reason='health_changed',
        )
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


def _timezone_name(session, user_id: str) -> str:
    profile = SqlAlchemyAthleteRaceRepository(session).get_profile_for_user(user_id)
    return profile.timezone if profile else 'UTC'
