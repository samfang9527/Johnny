"""Plan bounded historical activity detail enrichment without provider I/O."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select, text
from sqlalchemy.orm import Session, sessionmaker

from src.infrastructure.database.models import (
    ActivityModel, AthleteProfileModel, IntegrationConnectionModel, UserModel,
)


@dataclass(frozen=True)
class BackfillPlan:
    user_id: str
    activity_ids: tuple[str, ...]
    recent_count: int
    older_count: int


class ActivityDetailBackfill:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._factory = session_factory

    def plan(self, *, user_id: str, days: int = 28, now: datetime) -> BackfillPlan:
        if days < 1 or days > 365:
            raise ValueError('backfill days must be between 1 and 365')
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError('backfill now must be timezone-aware')
        with self._factory() as session:
            if session.bind.dialect.name == 'postgresql':
                session.execute(text('SET TRANSACTION READ ONLY'))
            if session.get(UserModel, user_id) is None:
                raise ValueError('user not found')
            timezone_name = session.scalar(select(AthleteProfileModel.timezone).where(
                AthleteProfileModel.user_id == user_id)) or 'UTC'
            zone = ZoneInfo(timezone_name)
            today = now.astimezone(zone).date()
            cutoff = today - timedelta(days=days)
            recent_cutoff = today - timedelta(days=7)
            activities = session.scalars(select(ActivityModel).join(
                IntegrationConnectionModel,
                ActivityModel.provider_connection_id == IntegrationConnectionModel.id).where(
                ActivityModel.user_id == user_id,
                ActivityModel.provider_activity_id.is_not(None),
                IntegrationConnectionModel.user_id == user_id,
                IntegrationConnectionModel.provider == 'garmin_connect',
                IntegrationConnectionModel.status == 'active')).all()
            selected = []
            for activity in activities:
                instant = activity.started_at.replace(tzinfo=timezone.utc) if activity.started_at.tzinfo is None else activity.started_at
                local_day = instant.astimezone(zone).date()
                if cutoff <= local_day < today:
                    selected.append((activity.id, instant, local_day))
        selected.sort(key=lambda row: (row[2] < recent_cutoff, -row[1].timestamp(), row[0]))
        recent_count = sum(day >= recent_cutoff for _, _, day in selected)
        return BackfillPlan(user_id=user_id, activity_ids=tuple(row[0] for row in selected),
                            recent_count=recent_count, older_count=len(selected) - recent_count)

    def enqueue(self, plan: BackfillPlan, *, service, now: datetime) -> tuple[str, ...]:
        batches = []
        for start in range(0, len(plan.activity_ids), 8):
            batch = service.start_batch(user_id=plan.user_id,
                activity_ids=plan.activity_ids[start:start + 8],
                source_sync_run_id=f'backfill:{plan.user_id}:{now.astimezone(timezone.utc).date().isoformat()}',
                now=now)
            batches.append(batch)
        return tuple(batches)
