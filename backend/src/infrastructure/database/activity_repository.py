from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.domain.activity_health import CompletedActivity, DailyHealthMetrics

from .models import ActivityModel, HealthMetricModel, IntegrationConnectionModel, IntegrationResourceCursorModel, utc_now


HEALTH_METRIC_TYPES = {
    "sleep_duration_minutes",
    "sleep_quality",
    "hrv_ms",
    "hrv_baseline_ms",
    "resting_heart_rate",
    "stress_score",
}


class SqlAlchemyActivityRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create_connection(
        self,
        *,
        user_id: str,
        provider: str,
        provider_account_id: str | None = None,
        provider_display_name: str | None = None,
        auth_scheme: str = "oauth2",
        credential_secret_ref: str | None = None,
        credential_format: str | None = None,
        capabilities: dict | None = None,
        provider_metadata: dict | None = None,
    ) -> IntegrationConnectionModel:
        connection = IntegrationConnectionModel(
            user_id=user_id,
            provider=provider,
            provider_account_id=provider_account_id,
            provider_display_name=provider_display_name,
            auth_scheme=auth_scheme,
            credential_secret_ref=credential_secret_ref,
            credential_format=credential_format,
            capabilities=capabilities or {},
            provider_metadata=provider_metadata or {},
        )
        self._session.add(connection)
        self._session.flush()
        return connection

    def record_credential_refresh(self, connection_id: str) -> IntegrationConnectionModel:
        connection = self._session.get(IntegrationConnectionModel, connection_id)
        if connection is None:
            raise ValueError(f"Integration connection not found: {connection_id}")
        refreshed_at = utc_now()
        connection.last_credential_refresh_at = refreshed_at
        connection.credential_rotated_at = refreshed_at
        self._session.flush()
        return connection

    def upsert_resource_cursor(
        self,
        *,
        integration_connection_id: str,
        resource_type: str,
        cursor_value: dict | None = None,
        sync_from: datetime | None = None,
        sync_until: datetime | None = None,
        status: str = "ready",
        metadata_json: dict | None = None,
    ) -> IntegrationResourceCursorModel:
        cursor = self._session.scalar(
            select(IntegrationResourceCursorModel).where(
                IntegrationResourceCursorModel.integration_connection_id == integration_connection_id,
                IntegrationResourceCursorModel.resource_type == resource_type,
            )
        )
        if cursor is None:
            cursor = IntegrationResourceCursorModel(
                integration_connection_id=integration_connection_id,
                resource_type=resource_type,
            )
            self._session.add(cursor)

        cursor.cursor_value = cursor_value or {}
        cursor.sync_from = sync_from
        cursor.sync_until = sync_until
        if status == "ready":
            cursor.last_successful_sync_at = utc_now()
        cursor.status = status
        cursor.metadata_json = metadata_json or {}
        self._session.flush()
        return cursor

    def list_for_user(
        self,
        user_id: str,
        *,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[ActivityModel]:
        statement = select(ActivityModel).where(ActivityModel.user_id == user_id).order_by(ActivityModel.started_at, ActivityModel.id)
        statement = _apply_paging(statement, limit=limit, offset=offset)
        return list(self._session.scalars(statement))

    def save_activity(self, user_id: str, activity: CompletedActivity) -> CompletedActivity | None:
        _ensure_matching_user_id(user_id, activity.user_id)
        model = self._get_activity_model(user_id, activity)
        if model is None:
            return None
        model.user_id = user_id
        model.provider_connection_id = activity.provider_connection_id
        model.provider_activity_id = activity.source_activity_id
        model.started_at = activity.started_at
        model.activity_type = activity.sport_type
        model.distance_meters = activity.distance_meters
        model.duration_seconds = activity.duration_seconds
        model.provider_summary = activity.to_summary()
        self._session.flush()
        return _activity_from_model(model)

    def get_activity_for_user(self, user_id: str, activity_id: str | None) -> CompletedActivity | None:
        if activity_id is None:
            return None
        model = self._session.scalar(
            select(ActivityModel).where(
                ActivityModel.id == activity_id,
                ActivityModel.user_id == user_id,
            )
        )
        if model is None:
            return None
        return _activity_from_model(model)

    def get_activity_by_provider_identifier(
        self,
        user_id: str,
        provider_connection_id: str,
        source_activity_id: str,
    ) -> CompletedActivity | None:
        model = self._session.scalar(
            select(ActivityModel).where(
                ActivityModel.user_id == user_id,
                ActivityModel.provider_connection_id == provider_connection_id,
                ActivityModel.provider_activity_id == source_activity_id,
            )
        )
        if model is None:
            return None
        return _activity_from_model(model)

    def list_activities_for_user(
        self,
        user_id: str,
        *,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[CompletedActivity]:
        statement = select(ActivityModel).where(ActivityModel.user_id == user_id).order_by(ActivityModel.started_at, ActivityModel.id)
        statement = _apply_paging(statement, limit=limit, offset=offset)
        return [_activity_from_model(model) for model in self._session.scalars(statement)]

    def list_activities_for_user_between(
        self,
        user_id: str,
        started_on_or_after: date,
        started_on_or_before: date,
        *,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[CompletedActivity]:
        statement = (
            select(ActivityModel)
            .where(
                ActivityModel.user_id == user_id,
                ActivityModel.started_at >= _measured_at(started_on_or_after),
                ActivityModel.started_at <= _end_of_day(started_on_or_before),
            )
            .order_by(ActivityModel.started_at, ActivityModel.id)
        )
        statement = _apply_paging(statement, limit=limit, offset=offset)
        return [_activity_from_model(model) for model in self._session.scalars(statement)]

    def save_daily_health_metrics(self, user_id: str, metrics: DailyHealthMetrics) -> DailyHealthMetrics:
        _ensure_matching_user_id(user_id, metrics.user_id)
        measured_at = _measured_at(metrics.metric_date)
        existing = list(
            self._session.scalars(
                select(HealthMetricModel).where(
                    HealthMetricModel.user_id == user_id,
                    HealthMetricModel.measured_at == measured_at,
                    HealthMetricModel.metric_type.in_(HEALTH_METRIC_TYPES),
                )
            )
        )
        for model in existing:
            self._session.delete(model)
        self._session.flush()

        for metric_type, value in metrics.values_by_metric_type().items():
            self._session.add(
                HealthMetricModel(
                    user_id=user_id,
                    measured_at=measured_at,
                    metric_type=metric_type,
                    value=value,
                    unit=_metric_unit(metric_type),
                    provider_summary={"source": metrics.source, "metric_date": metrics.metric_date.isoformat()},
                )
            )
        self._session.flush()
        return metrics

    def get_daily_health_metrics_for_user(self, user_id: str, metric_date: date) -> DailyHealthMetrics | None:
        measured_at = _measured_at(metric_date)
        models = list(
            self._session.scalars(
                select(HealthMetricModel).where(
                    HealthMetricModel.user_id == user_id,
                    HealthMetricModel.measured_at == measured_at,
                    HealthMetricModel.metric_type.in_(HEALTH_METRIC_TYPES),
                )
            )
        )
        if not models:
            return None

        values = {model.metric_type: model.value for model in models}
        source = next((model.provider_summary or {}).get("source") for model in models if model.provider_summary) or "manual"
        return DailyHealthMetrics.create(
            user_id=user_id,
            metric_date=metric_date,
            source=source,
            sleep_duration_minutes=values.get("sleep_duration_minutes"),
            sleep_quality=values.get("sleep_quality"),
            hrv_ms=values.get("hrv_ms"),
            hrv_baseline_ms=values.get("hrv_baseline_ms"),
            resting_heart_rate=values.get("resting_heart_rate"),
            stress_score=values.get("stress_score"),
        )

    def list_daily_health_metrics_for_user_between(
        self,
        user_id: str,
        measured_on_or_after: date,
        measured_on_or_before: date,
        *,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[DailyHealthMetrics]:
        statement = (
            select(HealthMetricModel)
            .where(
                HealthMetricModel.user_id == user_id,
                HealthMetricModel.measured_at >= _measured_at(measured_on_or_after),
                HealthMetricModel.measured_at <= _end_of_day(measured_on_or_before),
                HealthMetricModel.metric_type.in_(HEALTH_METRIC_TYPES),
            )
            .order_by(HealthMetricModel.measured_at, HealthMetricModel.metric_type)
        )
        grouped: dict[date, list[HealthMetricModel]] = defaultdict(list)
        for model in self._session.scalars(statement):
            grouped[model.measured_at.date()].append(model)

        metrics: list[DailyHealthMetrics] = []
        for metric_date in sorted(grouped):
            values = {model.metric_type: model.value for model in grouped[metric_date]}
            source = (
                next((model.provider_summary or {}).get("source") for model in grouped[metric_date] if model.provider_summary)
                or "manual"
            )
            metrics.append(
                DailyHealthMetrics.create(
                    user_id=user_id,
                    metric_date=metric_date,
                    source=source,
                    sleep_duration_minutes=values.get("sleep_duration_minutes"),
                    sleep_quality=values.get("sleep_quality"),
                    hrv_ms=values.get("hrv_ms"),
                    hrv_baseline_ms=values.get("hrv_baseline_ms"),
                    resting_heart_rate=values.get("resting_heart_rate"),
                    stress_score=values.get("stress_score"),
                )
            )
        return metrics[offset : offset + limit if limit is not None else None]

    def _get_activity_model(self, user_id: str, activity: CompletedActivity) -> ActivityModel | None:
        if activity.id is None:
            model = ActivityModel(
                user_id=user_id,
                started_at=activity.started_at,
                activity_type=activity.sport_type,
            )
            self._session.add(model)
            return model

        return self._session.scalar(
            select(ActivityModel).where(
                ActivityModel.id == activity.id,
                ActivityModel.user_id == user_id,
            )
        )


def _ensure_matching_user_id(trusted_user_id: str, payload_user_id: str) -> None:
    if trusted_user_id != payload_user_id:
        raise ValueError("payload user_id does not match repository user_id")


def _activity_from_model(model: ActivityModel) -> CompletedActivity:
    summary = model.provider_summary or {}
    return CompletedActivity.create(
        id=model.id,
        user_id=model.user_id,
        source=summary.get("source", "manual"),
        source_activity_id=model.provider_activity_id,
        provider_connection_id=model.provider_connection_id,
        started_at=model.started_at,
        sport_type=model.activity_type,
        distance_meters=model.distance_meters or 0,
        duration_seconds=model.duration_seconds or 0,
        average_pace_seconds_per_km=summary.get("average_pace_seconds_per_km"),
        average_heart_rate=summary.get("average_heart_rate"),
        elevation_gain_meters=summary.get("elevation_gain_meters"),
        matched_workout_id=summary.get("matched_workout_id"),
    )


def _measured_at(metric_date: date) -> datetime:
    return datetime.combine(metric_date, time.min, tzinfo=timezone.utc)


def _end_of_day(metric_date: date) -> datetime:
    return datetime.combine(metric_date, time.max, tzinfo=timezone.utc)


def _apply_paging(statement, *, limit: int | None, offset: int):  # noqa: ANN001
    if offset:
        statement = statement.offset(offset)
    if limit is not None:
        statement = statement.limit(limit)
    return statement


def _metric_unit(metric_type: str) -> str | None:
    return {
        "sleep_duration_minutes": "minutes",
        "sleep_quality": "score",
        "hrv_ms": "ms",
        "hrv_baseline_ms": "ms",
        "resting_heart_rate": "bpm",
        "stress_score": "score",
    }.get(metric_type)
