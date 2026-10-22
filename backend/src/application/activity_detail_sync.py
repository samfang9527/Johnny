"""Durable, owner-scoped activity detail acquisition and batch coordination."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Callable
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from src.application.integrations import GarminCredentialBlockedError, GarminRateLimitError
from src.application.interfaces.task_queue import TaskEnvelope
from src.domain.activity_details import DetailResource
from src.infrastructure.database.activity_detail_repository import SqlAlchemyActivityDetailRepository
from src.infrastructure.database.agent_task_queue import SqlAlchemyAgentTaskQueue
from src.infrastructure.database.integration_repository import SqlAlchemyIntegrationRepository
from src.infrastructure.database.models import (
    ActivityDetailBatchItemModel, ActivityDetailBatchModel, ActivityDetailFetchModel, AgentTaskModel,
    ActivityModel, AthleteProfileModel, IntegrationConnectionModel, UserModel,
)

FETCH_TASK = 'activity.detail.fetch.v1'
FINALIZE_TASK = 'activity.detail.finalize.v1'
RECHECK_TASK = 'activity.detail.recheck.v1'
DEFAULT_RESOURCES: tuple[DetailResource, ...] = (
    'fit', 'splits', 'details', 'hr_zones', 'typed_splits', 'split_summaries',
)
TERMINAL_ITEMS = frozenset(('changed', 'unchanged', 'failed', 'blocked', 'unsupported', 'timed_out'))
MAX_ATTEMPTS = 3
BATCH_DEADLINE = timedelta(seconds=120)
FETCH_LEASE = timedelta(minutes=5)


class ActivityDetailDeferred(RuntimeError):
    def __init__(self, delay: timedelta) -> None:
        super().__init__('activity detail work is temporarily deferred')
        self.delay = delay


class ActivityDetailRetry(RuntimeError):
    def __init__(self, delay: timedelta, category: str) -> None:
        super().__init__(category)
        self.delay = delay
        self.category = category


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError('activity detail timestamps must be timezone-aware')
    return value.astimezone(timezone.utc)


def _stored_utc(value: datetime) -> datetime:
    # SQLite returns timezone-naive values for timezone=True columns.
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _delay(attempt: int, exc: Exception) -> timedelta:
    base = 30 if attempt == 1 else 120
    # Stable jitter avoids synchronizing retries without making tests depend on randomness.
    jitter = (attempt * 7) % 11
    retry_after = getattr(exc, 'retry_after_seconds', None)
    seconds = max(base + jitter, retry_after if isinstance(retry_after, (int, float)) else 0)
    return timedelta(seconds=seconds)


class ActivityDetailSyncService:
    def __init__(self, session_factory: sessionmaker[Session],
                 adapter_factory: Callable[[Session], object], *,
                 resources: tuple[DetailResource, ...] = DEFAULT_RESOURCES) -> None:
        if not resources or len(set(resources)) != len(resources) or any(
                resource not in DEFAULT_RESOURCES for resource in resources):
            raise ValueError('unsupported activity detail resource selection')
        self._factory = session_factory
        self._adapter_factory = adapter_factory
        self._resources = resources

    def start_batch(self, *, user_id: str, activity_ids: tuple[str, ...],
                    source_sync_run_id: str | None, now: datetime) -> str:
        return self._start_batch(user_id=user_id, activity_ids=activity_ids,
                                 source_sync_run_id=source_sync_run_id, now=now,
                                 resources=self._resources)

    def _start_batch(self, *, user_id: str, activity_ids: tuple[str, ...],
                     source_sync_run_id: str | None, now: datetime,
                     resources: tuple[DetailResource, ...]) -> str:
        now = _utc(now)
        ids = tuple(dict.fromkeys(activity_ids))
        if not ids:
            raise ValueError('at least one activity is required')
        with self._factory() as session:
            owner = session.scalar(select(UserModel.id).where(UserModel.id == user_id).with_for_update())
            if owner is None:
                raise ValueError('activity owner not found')
            activities = session.execute(select(ActivityModel, IntegrationConnectionModel).join(
                IntegrationConnectionModel, ActivityModel.provider_connection_id == IntegrationConnectionModel.id)
                .where(ActivityModel.id.in_(ids), ActivityModel.user_id == user_id,
                       ActivityModel.provider_activity_id.is_not(None),
                       IntegrationConnectionModel.user_id == user_id,
                       IntegrationConnectionModel.provider == 'garmin_connect',
                       IntegrationConnectionModel.status == 'active')).all()
            if len(activities) != len(ids):
                raise ValueError('owned provider activity is required')
            resource_map = {}
            for activity, connection in activities:
                supported = (connection.capabilities or {}).get('activity_detail_resources')
                selected = tuple(resource for resource in resources if supported is None
                                 or resource in supported)
                if not selected:
                    raise ValueError('connection supports no requested activity detail resources')
                resource_map[activity.id] = selected
            open_batches = session.scalars(select(ActivityDetailBatchModel).where(
                ActivityDetailBatchModel.user_id == user_id,
                ActivityDetailBatchModel.source_sync_run_id == source_sync_run_id,
                ActivityDetailBatchModel.status.in_(('pending', 'paused'))).with_for_update()).all()
            expected = {(activity_id, resource) for activity_id in ids
                        for resource in resource_map[activity_id]}
            for existing in open_batches:
                members = set(session.execute(select(ActivityDetailBatchItemModel.activity_id,
                    ActivityDetailBatchItemModel.resource).where(
                    ActivityDetailBatchItemModel.batch_id == existing.id)).all())
                if members == expected:
                    return existing.id
            batch = ActivityDetailBatchModel(user_id=user_id, source_sync_run_id=source_sync_run_id,
                                             status='pending', deadline_at=now + BATCH_DEADLINE)
            session.add(batch)
            session.flush()
            queue = SqlAlchemyAgentTaskQueue(session)
            pending_count = 0
            for activity_id in ids:
                for resource in resource_map[activity_id]:
                    fetch = session.scalar(select(ActivityDetailFetchModel).where(
                        ActivityDetailFetchModel.user_id == user_id,
                        ActivityDetailFetchModel.activity_id == activity_id,
                        ActivityDetailFetchModel.resource == resource).with_for_update())
                    if fetch is None:
                        fetch = ActivityDetailFetchModel(user_id=user_id, activity_id=activity_id,
                                                         resource=resource, status='pending')
                        session.add(fetch)
                        session.flush()
                    connection = next(conn for activity, conn in activities if activity.id == activity_id)
                    if fetch.status == 'unsupported':
                        item_status = 'unsupported'
                    elif fetch.status == 'blocked' and connection.credential_status != 'active':
                        item_status = 'blocked'
                    else:
                        item_status = 'pending'
                        if fetch.status in ('failed', 'blocked'):
                            fetch.status = 'pending'
                            fetch.retry_count = 0
                            fetch.next_retry_at = None
                    item = ActivityDetailBatchItemModel(user_id=user_id, batch_id=batch.id,
                        activity_id=activity_id, resource=resource, fetch_id=fetch.id, status=item_status)
                    session.add(item)
                    session.flush()
                    if item_status == 'pending':
                        pending_count += 1
                        queue.enqueue(TaskEnvelope(task_type=FETCH_TASK,
                            payload={'fetch_id': fetch.id, 'batch_id': batch.id, 'item_id': item.id},
                            correlation_id=batch.id, idempotency_key=f'{FETCH_TASK}:{item.id}',
                            available_at=now, max_attempts=MAX_ATTEMPTS))
            queue.enqueue(TaskEnvelope(task_type=FINALIZE_TASK,
                payload={'batch_id': batch.id}, correlation_id=batch.id,
                idempotency_key=f'{FINALIZE_TASK}:{batch.id}',
                available_at=batch.deadline_at if pending_count else now,
                max_attempts=MAX_ATTEMPTS))
            session.commit()
            return batch.id

    def process_resource(self, *, fetch_id: str, now: datetime) -> None:
        now = _utc(now)
        with self._factory() as session:
            fetch = session.scalar(select(ActivityDetailFetchModel).where(
                ActivityDetailFetchModel.id == fetch_id).with_for_update())
            if fetch is None:
                return
            items = session.scalars(select(ActivityDetailBatchItemModel).join(
                ActivityDetailBatchModel, ActivityDetailBatchItemModel.batch_id == ActivityDetailBatchModel.id)
                .where(ActivityDetailBatchItemModel.fetch_id == fetch_id,
                       ActivityDetailBatchItemModel.status.not_in(TERMINAL_ITEMS),
                       ActivityDetailBatchModel.status != 'closed')
                .order_by(ActivityDetailBatchItemModel.created_at, ActivityDetailBatchItemModel.id)).all()
            if not items:
                return
            batch = session.get(ActivityDetailBatchModel, items[0].batch_id)
            if batch.status == 'paused':
                raise ActivityDetailDeferred(timedelta(seconds=30))
            lease_until = _stored_utc(fetch.next_retry_at) if fetch.next_retry_at else None
            if fetch.status in ('fetching', 'retry_wait') and lease_until and lease_until > now:
                raise ActivityDetailDeferred(lease_until - now)
            activity = session.scalar(select(ActivityModel).where(
                ActivityModel.id == fetch.activity_id, ActivityModel.user_id == fetch.user_id,
                ActivityModel.provider_activity_id.is_not(None)))
            connection = session.scalar(select(IntegrationConnectionModel).where(
                IntegrationConnectionModel.id == activity.provider_connection_id,
                IntegrationConnectionModel.user_id == fetch.user_id,
                IntegrationConnectionModel.provider == 'garmin_connect',
                IntegrationConnectionModel.status == 'active')) if activity else None
            if connection is None:
                for item in items:
                    item.status = 'blocked'
                fetch.status = 'blocked'
                fetch.last_error_type = 'ConnectionUnavailable'
                session.commit()
                return
            if connection.credential_status != 'active':
                for item in items:
                    item.status = 'blocked'
                fetch.status = 'blocked'
                fetch.last_error_type = 'GarminRequiresReauth'
                session.commit()
                return
            connection_id = connection.id
            provider_id = activity.provider_activity_id
            user_id = fetch.user_id
            activity_id = activity.id
            resource = fetch.resource
            fetch.status = 'fetching'
            fetch.next_retry_at = now + FETCH_LEASE
            for item in items:
                item.status = 'fetching'
            session.commit()  # Persist the claim before any provider call.

        try:
            with self._factory() as provider_session:
                connection_ref = SqlAlchemyIntegrationRepository(provider_session).get_connection_for_user(
                    user_id, connection_id)
                details = self._adapter_factory(provider_session).fetch_activity_detail(
                    connection=connection_ref, activity_id=activity_id, resource=resource,
                    provider_activity_id=provider_id)
                provider_session.commit()  # Commit refreshed encrypted credential only on success.
        except Exception as exc:
            self._record_failure(fetch_id=fetch_id, now=now, exc=exc)
            return

        with self._factory() as session:
            fetch = session.scalar(select(ActivityDetailFetchModel).where(
                ActivityDetailFetchModel.id == fetch_id).with_for_update())
            before = fetch.current_snapshot_id
            snapshot = SqlAlchemyActivityDetailRepository(session).save_snapshot(
                user_id=user_id, details=details, fetched_at=now)
            fetch.status = 'available' if details.coverage.state == 'complete' else 'partial'
            fetch.next_retry_at = None
            pending = session.scalars(select(ActivityDetailBatchItemModel).join(
                ActivityDetailBatchModel, ActivityDetailBatchItemModel.batch_id == ActivityDetailBatchModel.id)
                .where(ActivityDetailBatchItemModel.fetch_id == fetch_id,
                       ActivityDetailBatchItemModel.status.not_in(TERMINAL_ITEMS),
                       ActivityDetailBatchModel.status != 'closed')
                .order_by(ActivityDetailBatchItemModel.created_at, ActivityDetailBatchItemModel.id)).all()
            for index, item in enumerate(pending):
                item.status = 'changed' if before != snapshot.id and index == 0 else 'unchanged'
            self._expedite_ready_batches(session, pending, now)
            session.commit()

    def _record_failure(self, *, fetch_id: str, now: datetime, exc: Exception) -> None:
        blocked = isinstance(exc, GarminCredentialBlockedError)
        response = getattr(exc, 'response', None)
        unsupported = getattr(response, 'status_code', None) == 404
        category = ('GarminRequiresReauth' if blocked else 'UnsupportedResource' if unsupported
                    else 'RateLimited' if isinstance(exc, GarminRateLimitError) else 'ProviderFailure')
        with self._factory() as session:
            fetch = session.scalar(select(ActivityDetailFetchModel).where(
                ActivityDetailFetchModel.id == fetch_id).with_for_update())
            if fetch is None:
                return
            fetch.retry_count += 1
            fetch.last_error_type = category
            terminal = blocked or unsupported or fetch.retry_count >= MAX_ATTEMPTS
            delay = _delay(fetch.retry_count, exc)
            fetch.status = 'blocked' if blocked else 'unsupported' if unsupported else 'failed' if terminal else 'retry_wait'
            fetch.next_retry_at = None if terminal else now + delay
            items = session.scalars(select(ActivityDetailBatchItemModel).where(
                ActivityDetailBatchItemModel.fetch_id == fetch_id,
                ActivityDetailBatchItemModel.status.not_in(TERMINAL_ITEMS))).all()
            for item in items:
                item.status = fetch.status if terminal else 'pending'
            if blocked:
                activity = session.get(ActivityModel, fetch.activity_id)
                if activity is not None:
                    SqlAlchemyIntegrationRepository(session).mark_connection_requires_reauth(
                        activity.provider_connection_id, 'Garmin connection requires reauth')
            self._expedite_ready_batches(session, items, now)
            session.commit()
        if not terminal:
            raise ActivityDetailRetry(delay, category)

    @staticmethod
    def _expedite_ready_batches(session: Session, items: list[ActivityDetailBatchItemModel],
                                now: datetime) -> None:
        queue = SqlAlchemyAgentTaskQueue(session)
        for batch_id in {item.batch_id for item in items}:
            remaining = session.scalar(select(ActivityDetailBatchItemModel.id).where(
                ActivityDetailBatchItemModel.batch_id == batch_id,
                ActivityDetailBatchItemModel.status.not_in(TERMINAL_ITEMS)).limit(1))
            if remaining is None:
                queue.expedite(f'{FINALIZE_TASK}:{batch_id}', now=now)

    def finalize_batch(self, *, batch_id: str, now: datetime) -> tuple[str, ...]:
        now = _utc(now)
        with self._factory() as session:
            batch = session.scalar(select(ActivityDetailBatchModel).where(
                ActivityDetailBatchModel.id == batch_id).with_for_update())
            if batch is None or batch.status == 'closed':
                return ()
            if batch.status == 'paused':
                raise ActivityDetailDeferred(timedelta(seconds=30))
            items = session.scalars(select(ActivityDetailBatchItemModel).where(
                ActivityDetailBatchItemModel.batch_id == batch_id).with_for_update()).all()
            incomplete = [item for item in items if item.status not in TERMINAL_ITEMS]
            if incomplete and now < _stored_utc(batch.deadline_at):
                raise ActivityDetailDeferred(_stored_utc(batch.deadline_at) - now)
            for item in incomplete:
                item.status = 'timed_out'
            changed = tuple(sorted({item.activity_id for item in items if item.status == 'changed'}))
            fetches = {fetch.id: fetch for fetch in session.scalars(select(ActivityDetailFetchModel).where(
                ActivityDetailFetchModel.id.in_({item.fetch_id for item in items}))).all()}
            partial = bool(incomplete or any(
                item.status not in ('changed', 'unchanged')
                or fetches[item.fetch_id].status != 'available' for item in items))
            batch.status = 'closed'
            batch.closed_at = now
            finalizer = session.scalar(select(AgentTaskModel).where(
                AgentTaskModel.idempotency_key == f'{FINALIZE_TASK}:{batch_id}').with_for_update())
            if finalizer is not None:
                finalizer.payload = {**(finalizer.payload or {}), 'changed_activity_ids': list(changed),
                                     'closed_at': now.isoformat(), 'partial': partial}
            if not (batch.source_sync_run_id or '').startswith('recheck:'):
                self._schedule_late_rechecks(session, batch, items, fetches, now)
            session.commit()
            return changed

    @staticmethod
    def _schedule_late_rechecks(session: Session, batch: ActivityDetailBatchModel,
                                items: list[ActivityDetailBatchItemModel],
                                fetches: dict[str, ActivityDetailFetchModel], now: datetime) -> None:
        timezone_name = session.scalar(select(AthleteProfileModel.timezone).where(
            AthleteProfileModel.user_id == batch.user_id)) or 'UTC'
        zone = ZoneInfo(timezone_name)
        today = now.astimezone(zone).date()
        queue = SqlAlchemyAgentTaskQueue(session)
        for item in items:
            fetch = fetches[item.fetch_id]
            if fetch.status not in ('partial', 'pending', 'retry_wait', 'fetching'):
                continue
            if fetch.status != 'partial' and item.status != 'timed_out':
                continue
            activity = session.get(ActivityModel, item.activity_id)
            if activity is None:
                continue
            started = _stored_utc(activity.started_at)
            if not today - timedelta(days=1) <= started.astimezone(zone).date() <= today:
                continue
            for ordinal, delay in ((1, timedelta(minutes=15)), (2, timedelta(hours=2))):
                queue.enqueue(TaskEnvelope(task_type=RECHECK_TASK,
                    payload={'user_id': batch.user_id, 'activity_id': item.activity_id,
                             'resource': item.resource, 'origin_batch_id': batch.id,
                             'ordinal': ordinal},
                    correlation_id=batch.id,
                    idempotency_key=f'{RECHECK_TASK}:{batch.id}:{item.activity_id}:{item.resource}:{ordinal}',
                    available_at=now + delay, max_attempts=MAX_ATTEMPTS))

    def run_recheck(self, *, user_id: str, activity_id: str, resource: DetailResource,
                    origin_batch_id: str, ordinal: int, now: datetime) -> str | None:
        if ordinal not in (1, 2) or resource not in DEFAULT_RESOURCES:
            raise ValueError('unsupported activity detail recheck')
        with self._factory() as session:
            original = session.scalar(select(ActivityDetailBatchItemModel).join(
                ActivityDetailBatchModel, ActivityDetailBatchItemModel.batch_id == ActivityDetailBatchModel.id)
                .where(ActivityDetailBatchItemModel.batch_id == origin_batch_id,
                       ActivityDetailBatchItemModel.activity_id == activity_id,
                       ActivityDetailBatchItemModel.resource == resource,
                       ActivityDetailBatchItemModel.user_id == user_id,
                       ActivityDetailBatchModel.user_id == user_id,
                       ActivityDetailBatchModel.status == 'closed'))
            if original is None:
                raise ValueError('owned closed batch item is required')
            fetch = session.get(ActivityDetailFetchModel, original.fetch_id)
            if fetch is None or (fetch.status != 'partial' and not (
                    original.status == 'timed_out'
                    and fetch.status in ('pending', 'retry_wait', 'fetching'))):
                return None
        return self._start_batch(user_id=user_id, activity_ids=(activity_id,),
            source_sync_run_id=f'recheck:{origin_batch_id}:{ordinal}', now=now,
            resources=(resource,))

    def pause_batch(self, *, user_id: str, batch_id: str) -> None:
        with self._factory() as session:
            batch = session.scalar(select(ActivityDetailBatchModel).where(
                ActivityDetailBatchModel.id == batch_id,
                ActivityDetailBatchModel.user_id == user_id).with_for_update())
            if batch is None or batch.status == 'closed':
                raise ValueError('active owned batch is required')
            batch.status = 'paused'
            session.commit()

    def resume_batch(self, *, user_id: str, batch_id: str, now: datetime) -> str:
        now = _utc(now)
        with self._factory() as session:
            batch = session.scalar(select(ActivityDetailBatchModel).where(
                ActivityDetailBatchModel.id == batch_id,
                ActivityDetailBatchModel.user_id == user_id).with_for_update())
            if batch is None or batch.status == 'closed':
                raise ValueError('active owned batch is required')
            batch.status = 'pending'
            queue = SqlAlchemyAgentTaskQueue(session)
            if _stored_utc(batch.deadline_at) <= now:
                batch.deadline_at = now + BATCH_DEADLINE
                queue.reschedule(f'{FINALIZE_TASK}:{batch.id}', available_at=batch.deadline_at,
                                 now=now)
            items = session.scalars(select(ActivityDetailBatchItemModel).where(
                ActivityDetailBatchItemModel.batch_id == batch_id)).all()
            for item in items:
                if item.status not in TERMINAL_ITEMS:
                    queue.expedite(f'{FETCH_TASK}:{item.id}', now=now)
            session.commit()
            return batch.id
