"""One current Daily Advice per athlete/day with input-version guarded writes."""

from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import and_, case, or_, select, update
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from src.domain.daily_advice import AdviceSections, DailyAdvice, RefreshVersion, WeekExecution, WorkoutGuide

from .models import DailyAdviceModel, utc_now, uuid_string


class SqlAlchemyDailyAdviceRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_for_user_date(self, user_id: str, advice_date: date) -> DailyAdvice | None:
        model = self._session.scalar(
            select(DailyAdviceModel)
            .where(DailyAdviceModel.user_id == user_id, DailyAdviceModel.advice_date == advice_date)
            .execution_options(populate_existing=True)
        )
        return _advice_from_model(model) if model is not None else None

    def begin_refresh(
        self,
        user_id: str,
        advice_date: date,
        version: RefreshVersion,
        source_sync_run_id: str | None,
    ) -> bool:
        now = utc_now()
        insert = _insert_for_session(self._session).values(
            id=uuid_string(),
            user_id=user_id,
            advice_date=advice_date,
            state="pending",
            data_freshness="limited",
            reserved_observed_at=version.observed_at,
            reserved_run_id=version.run_id,
            refresh_source_sync_run_id=source_sync_run_id,
            created_at=now,
            updated_at=now,
        )
        statement = insert.on_conflict_do_update(
            index_elements=[DailyAdviceModel.user_id, DailyAdviceModel.advice_date],
            set_={
                "state": "pending",
                "data_freshness": case((DailyAdviceModel.generated_at.is_not(None), "stale"), else_="limited"),
                "reserved_observed_at": version.observed_at,
                "reserved_run_id": version.run_id,
                "refresh_source_sync_run_id": source_sync_run_id,
                "updated_at": now,
            },
            where=_older_than(version),
        )
        if self._session.execute(statement).rowcount == 1:
            return True
        existing = self._session.execute(
            select(
                DailyAdviceModel.reserved_observed_at,
                DailyAdviceModel.reserved_run_id,
                DailyAdviceModel.refresh_source_sync_run_id,
            ).where(DailyAdviceModel.user_id == user_id, DailyAdviceModel.advice_date == advice_date)
        ).one_or_none()
        return bool(
            existing is not None
            and RefreshVersion(existing.reserved_observed_at, existing.reserved_run_id) == version
            and existing.refresh_source_sync_run_id == source_sync_run_id
        )

    def publish(
        self,
        user_id: str,
        advice_date: date,
        version: RefreshVersion,
        advice: DailyAdvice,
    ) -> bool:
        if (
            advice.user_id != user_id or advice.advice_date != advice_date
            or advice.source_run_id != version.run_id or advice.state != "ready"
        ):
            return False
        if advice.facts is None or advice.sections is None or advice.generated_at is None:
            return False
        statement = (
            update(DailyAdviceModel)
            .where(
                DailyAdviceModel.user_id == user_id,
                DailyAdviceModel.advice_date == advice_date,
                *_reserved_version_matches(version),
                DailyAdviceModel.refresh_source_sync_run_id.is_not_distinct_from(advice.source_sync_run_id),
                DailyAdviceModel.state == "pending",
            )
            .values(
                state="ready",
                data_freshness=advice.data_freshness,
                plan_version_id=advice.plan_version_id,
                workout_id=advice.workout_id,
                week_start=advice.week_start,
                week_end=advice.week_end,
                execution_mode=advice.execution_mode,
                facts=advice.facts.to_payload(),
                week_summary=advice.sections.week_summary,
                today_execution=advice.sections.today_execution,
                workout_guide=advice.sections.workout_guide.to_payload(),
                generated_at=_as_utc(advice.generated_at),
                source_sync_run_id=advice.source_sync_run_id,
                source_run_id=advice.source_run_id,
                updated_at=utc_now(),
            )
        )
        if self._session.execute(statement).rowcount == 1:
            return True
        existing = self.get_for_user_date(user_id, advice_date)
        return bool(
            existing is not None and existing.refresh_version == version
            and existing.state == "ready" and existing.source_run_id == version.run_id
            and existing.source_sync_run_id == advice.source_sync_run_id
        )

    def mark_failed(self, user_id: str, advice_date: date, version: RefreshVersion, state: str) -> bool:
        if state not in {"sync_failed", "generation_failed", "no_plan"}:
            raise ValueError("daily advice failure state is invalid")
        statement = (
            update(DailyAdviceModel)
            .where(
                DailyAdviceModel.user_id == user_id,
                DailyAdviceModel.advice_date == advice_date,
                *_reserved_version_matches(version),
                DailyAdviceModel.state == "pending",
            )
            .values(
                state=state,
                data_freshness=case((DailyAdviceModel.generated_at.is_not(None), "stale"), else_="limited"),
                updated_at=utc_now(),
            )
        )
        if self._session.execute(statement).rowcount == 1:
            return True
        existing = self.get_for_user_date(user_id, advice_date)
        return bool(existing is not None and existing.refresh_version == version and existing.state == state)


def _insert_for_session(session: Session):
    dialect = session.get_bind().dialect.name
    if dialect == "sqlite":
        return sqlite_insert(DailyAdviceModel)
    if dialect == "postgresql":
        return postgres_insert(DailyAdviceModel)
    raise RuntimeError(f"Daily Advice persistence does not support {dialect}")


def _older_than(version: RefreshVersion):
    return or_(
        DailyAdviceModel.reserved_observed_at < version.observed_at,
        and_(
            DailyAdviceModel.reserved_observed_at == version.observed_at,
            DailyAdviceModel.reserved_run_id < version.run_id,
        ),
    )


def _reserved_version_matches(version: RefreshVersion):
    return (
        DailyAdviceModel.reserved_observed_at == version.observed_at,
        DailyAdviceModel.reserved_run_id == version.run_id,
    )


def _advice_from_model(model: DailyAdviceModel) -> DailyAdvice:
    sections = None
    if model.week_summary is not None and model.today_execution is not None and model.workout_guide is not None:
        sections = AdviceSections(
            week_summary=model.week_summary,
            today_execution=model.today_execution,
            workout_guide=WorkoutGuide.from_payload(model.workout_guide),
        )
    return DailyAdvice(
        id=model.id,
        user_id=model.user_id,
        advice_date=model.advice_date,
        plan_version_id=model.plan_version_id,
        workout_id=model.workout_id,
        week_start=model.week_start,
        week_end=model.week_end,
        execution_mode=model.execution_mode,
        facts=WeekExecution.from_payload(model.facts) if model.facts is not None else None,
        sections=sections,
        generated_at=_as_utc(model.generated_at) if model.generated_at is not None else None,
        source_sync_run_id=model.source_sync_run_id,
        source_run_id=model.source_run_id,
        state=model.state,
        data_freshness=model.data_freshness,
        refresh_version=RefreshVersion(model.reserved_observed_at, model.reserved_run_id),
        refresh_source_sync_run_id=model.refresh_source_sync_run_id,
    )


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
