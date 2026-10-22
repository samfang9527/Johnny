"""Durable activity-detail batches keep provider I/O outside generation."""
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Event
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

from src.application.activity_detail_sync import (
    ActivityDetailDeferred, ActivityDetailRetry, ActivityDetailSyncService,
)
from src.application.integrations import GarminCredentialBlockedError, GarminRateLimitError
from src.domain.activity_details import ActivitySampleChunk, DetailCoverage, NormalizedDetails
from src.infrastructure.database.models import (
    ActivityDetailBatchItemModel, ActivityDetailBatchModel, ActivityDetailFetchModel, ActivityDetailSnapshotModel,
    AgentTaskModel,
    ActivityModel, Base, IntegrationConnectionModel, UserModel,
)

NOW = datetime(2026, 10, 23, 8, tzinfo=timezone.utc)


class Provider:
    def __init__(self, outcomes=()):
        self.outcomes = list(outcomes)
        self.calls = []

    def fetch_activity_detail(self, *, connection, activity_id, resource, provider_activity_id):
        self.calls.append((connection.id, activity_id, resource, provider_activity_id))
        outcome = self.outcomes.pop(0) if self.outcomes else None
        if isinstance(outcome, Exception):
            raise outcome
        return outcome or NormalizedDetails(
            activity_id=activity_id, resource=resource, schema_version='test-v1',
            coverage=DetailCoverage(state='complete', sampling='recorded'),
            sample_chunks=(ActivitySampleChunk(ordinal=0, samples=({'elapsed_seconds': 1},)),),
        )


@pytest.fixture
def seeded(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'detail-sync.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        session.add_all([
            UserModel(id='owner', email='owner@example.invalid', display_name='Owner'),
            UserModel(id='other', email='other@example.invalid', display_name='Other'),
        ])
        session.flush()
        session.add_all([
            IntegrationConnectionModel(id='connection', user_id='owner', provider='garmin_connect'),
            IntegrationConnectionModel(id='foreign-connection', user_id='other', provider='garmin_connect'),
        ])
        session.flush()
        session.add_all([
            ActivityModel(id='run', user_id='owner', provider_connection_id='connection',
                          provider_activity_id='provider-run', started_at=NOW - timedelta(days=1),
                          activity_type='running'),
            ActivityModel(id='manual', user_id='owner', started_at=NOW - timedelta(days=1),
                          activity_type='running'),
            ActivityModel(id='foreign', user_id='other', provider_connection_id='foreign-connection',
                          provider_activity_id='provider-run', started_at=NOW - timedelta(days=1),
                          activity_type='running'),
        ])
        session.commit()
    yield factory
    engine.dispose()


def _item(factory, batch_id):
    with factory() as session:
        return session.scalar(select(ActivityDetailBatchItemModel).where(
            ActivityDetailBatchItemModel.batch_id == batch_id))


def test_crash_after_snapshot_commit_replays_without_duplicate_or_early_generation(seeded):
    provider = Provider()
    generation_calls = []
    service = ActivityDetailSyncService(seeded, lambda session: provider, resources=('fit',))
    batch_id = service.start_batch(user_id='owner', activity_ids=('run',),
                                   source_sync_run_id='sync-1', now=NOW)
    fetch_id = _item(seeded, batch_id).fetch_id
    assert service.start_batch(user_id='owner', activity_ids=('run',),
                               source_sync_run_id='sync-1', now=NOW) == batch_id

    service.process_resource(fetch_id=fetch_id, now=NOW + timedelta(seconds=1))
    assert generation_calls == []
    service.process_resource(fetch_id=fetch_id, now=NOW + timedelta(seconds=2))
    with seeded() as session:
        assert session.scalar(select(func.count()).select_from(ActivityDetailSnapshotModel)) == 1
    assert service.finalize_batch(batch_id=batch_id, now=NOW + timedelta(seconds=3)) == ('run',)
    assert service.finalize_batch(batch_id=batch_id, now=NOW + timedelta(seconds=4)) == ()
    with seeded() as session:
        finalizer = session.scalar(select(AgentTaskModel).where(
            AgentTaskModel.idempotency_key == f'activity.detail.finalize.v1:{batch_id}'))
        assert finalizer.payload['changed_activity_ids'] == ['run']
    assert len(provider.calls) == 1


def test_deadline_closes_partial_batch_even_without_resource_completion(seeded):
    service = ActivityDetailSyncService(seeded, lambda session: Provider(), resources=('fit',))
    batch_id = service.start_batch(user_id='owner', activity_ids=('run',),
                                   source_sync_run_id=None, now=NOW)
    with pytest.raises(ActivityDetailDeferred):
        service.finalize_batch(batch_id=batch_id, now=NOW + timedelta(seconds=119))
    with seeded() as session:
        assert session.get(ActivityDetailBatchModel, batch_id).status != 'closed'
    assert service.finalize_batch(batch_id=batch_id, now=NOW + timedelta(seconds=120)) == ()
    with seeded() as session:
        assert session.get(ActivityDetailBatchModel, batch_id).status == 'closed'


def test_foreign_and_manual_activities_cannot_be_queued(seeded):
    service = ActivityDetailSyncService(seeded, lambda session: Provider(), resources=('fit',))
    with pytest.raises(ValueError, match='owned provider activity'):
        service.start_batch(user_id='owner', activity_ids=('foreign',),
                            source_sync_run_id=None, now=NOW)
    with pytest.raises(ValueError, match='owned provider activity'):
        service.start_batch(user_id='owner', activity_ids=('manual',),
                            source_sync_run_id=None, now=NOW)


def test_connection_capabilities_limit_requested_resources(seeded):
    with seeded() as session:
        session.get(IntegrationConnectionModel, 'connection').capabilities = {
            'activity_detail_resources': ['fit', 'details']}
        session.commit()
    service = ActivityDetailSyncService(seeded, lambda session: Provider())
    batch = service.start_batch(user_id='owner', activity_ids=('run',),
                                source_sync_run_id='capability', now=NOW)
    with seeded() as session:
        resources = set(session.scalars(select(ActivityDetailBatchItemModel.resource).where(
            ActivityDetailBatchItemModel.batch_id == batch)).all())
        assert resources == {'fit', 'details'}


def test_not_found_resource_is_not_polled_again_in_later_batches(seeded):
    class NotFound(Exception):
        response = SimpleNamespace(status_code=404)

    provider = Provider([NotFound()])
    service = ActivityDetailSyncService(seeded, lambda session: provider, resources=('fit',))
    first = service.start_batch(user_id='owner', activity_ids=('run',),
                                source_sync_run_id='first-404', now=NOW)
    fetch_id = _item(seeded, first).fetch_id
    service.process_resource(fetch_id=fetch_id, now=NOW + timedelta(seconds=1))
    service.finalize_batch(batch_id=first, now=NOW + timedelta(seconds=2))
    second = service.start_batch(user_id='owner', activity_ids=('run',),
                                 source_sync_run_id='second-404', now=NOW + timedelta(seconds=3))
    service.process_resource(fetch_id=fetch_id, now=NOW + timedelta(seconds=4))
    assert service.finalize_batch(batch_id=second, now=NOW + timedelta(seconds=5)) == ()
    assert len(provider.calls) == 1
    with seeded() as session:
        assert _item(seeded, second).status == 'unsupported'
        assert session.scalar(select(func.count()).select_from(AgentTaskModel).where(
            AgentTaskModel.correlation_id == second,
            AgentTaskModel.task_type == 'activity.detail.fetch.v1')) == 0


def test_rate_limit_honors_retry_after_and_preserves_old_snapshot(seeded):
    provider = Provider()
    service = ActivityDetailSyncService(seeded, lambda session: provider, resources=('fit',))
    original = service.start_batch(user_id='owner', activity_ids=('run',),
                                   source_sync_run_id='first', now=NOW)
    fetch_id = _item(seeded, original).fetch_id
    service.process_resource(fetch_id=fetch_id, now=NOW)
    with seeded() as session:
        previous = session.get(ActivityDetailFetchModel, fetch_id).current_snapshot_id
    service.finalize_batch(batch_id=original, now=NOW + timedelta(seconds=1))

    provider.outcomes = [GarminRateLimitError(retry_after_seconds=90)]
    second = service.start_batch(user_id='owner', activity_ids=('run',),
                                 source_sync_run_id='second', now=NOW + timedelta(seconds=2))
    with pytest.raises(ActivityDetailRetry) as retry:
        service.process_resource(fetch_id=fetch_id, now=NOW + timedelta(seconds=3))
    assert retry.value.delay >= timedelta(seconds=90)
    with seeded() as session:
        fetch = session.get(ActivityDetailFetchModel, fetch_id)
        assert fetch.current_snapshot_id == previous
        assert fetch.status == 'retry_wait'
        assert fetch.retry_count == 1
    with pytest.raises(ActivityDetailDeferred):
        service.process_resource(fetch_id=fetch_id, now=NOW + timedelta(seconds=30))
    service.process_resource(fetch_id=fetch_id, now=NOW + timedelta(seconds=94))
    assert service.finalize_batch(batch_id=second, now=NOW + timedelta(seconds=95)) == ()
    with seeded() as session:
        assert session.scalar(select(func.count()).select_from(ActivityDetailSnapshotModel)) == 1


def test_authentication_failure_blocks_fetch_without_erasing_previous_evidence(seeded):
    provider = Provider()
    service = ActivityDetailSyncService(seeded, lambda session: provider, resources=('fit',))
    first = service.start_batch(user_id='owner', activity_ids=('run',),
                                source_sync_run_id='one', now=NOW)
    fetch_id = _item(seeded, first).fetch_id
    service.process_resource(fetch_id=fetch_id, now=NOW)
    service.finalize_batch(batch_id=first, now=NOW + timedelta(seconds=1))
    provider.outcomes = [GarminCredentialBlockedError()]
    second = service.start_batch(user_id='owner', activity_ids=('run',),
                                 source_sync_run_id='two', now=NOW + timedelta(seconds=2))
    service.process_resource(fetch_id=fetch_id, now=NOW + timedelta(seconds=3))
    assert service.finalize_batch(batch_id=second, now=NOW + timedelta(seconds=4)) == ()
    with seeded() as session:
        fetch = session.get(ActivityDetailFetchModel, fetch_id)
        assert fetch.current_snapshot_id is not None
        assert fetch.status == 'blocked'
        assert session.get(IntegrationConnectionModel, 'connection').credential_status == 'requires_reauth'
        session.get(IntegrationConnectionModel, 'connection').credential_status = 'active'
        session.commit()
    recovered = service.start_batch(user_id='owner', activity_ids=('run',),
                                    source_sync_run_id='after-reauth', now=NOW + timedelta(minutes=1))
    service.process_resource(fetch_id=fetch_id, now=NOW + timedelta(minutes=1, seconds=1))
    assert service.finalize_batch(batch_id=recovered,
                                  now=NOW + timedelta(minutes=1, seconds=2)) == ()
    with seeded() as session:
        assert session.get(ActivityDetailFetchModel, fetch_id).status == 'available'


def test_overlapping_manual_and_backfill_batches_share_one_fetch_result(seeded):
    provider = Provider()
    service = ActivityDetailSyncService(seeded, lambda session: provider, resources=('fit',))
    manual = service.start_batch(user_id='owner', activity_ids=('run',),
                                 source_sync_run_id=None, now=NOW)
    backfill = service.start_batch(user_id='owner', activity_ids=('run',),
                                   source_sync_run_id='backfill', now=NOW)
    fetch_id = _item(seeded, manual).fetch_id
    assert _item(seeded, backfill).fetch_id == fetch_id
    service.process_resource(fetch_id=fetch_id, now=NOW + timedelta(seconds=1))
    assert service.finalize_batch(batch_id=manual, now=NOW + timedelta(seconds=2)) == ('run',)
    assert service.finalize_batch(batch_id=backfill, now=NOW + timedelta(seconds=2)) == ()
    assert len(provider.calls) == 1


def test_paused_batch_preserves_checkpoint_and_resume_only_requeues_pending(seeded):
    provider = Provider()
    service = ActivityDetailSyncService(seeded, lambda session: provider, resources=('fit', 'splits'))
    batch = service.start_batch(user_id='owner', activity_ids=('run',),
                                source_sync_run_id='pause', now=NOW)
    with seeded() as session:
        items = session.scalars(select(ActivityDetailBatchItemModel).where(
            ActivityDetailBatchItemModel.batch_id == batch)).all()
    service.process_resource(fetch_id=items[0].fetch_id, now=NOW)
    service.pause_batch(user_id='owner', batch_id=batch)
    with pytest.raises(ActivityDetailDeferred):
        service.process_resource(fetch_id=items[1].fetch_id, now=NOW + timedelta(seconds=1))
    assert len(provider.calls) == 1
    service.resume_batch(user_id='owner', batch_id=batch, now=NOW + timedelta(seconds=2))
    service.process_resource(fetch_id=items[1].fetch_id, now=NOW + timedelta(seconds=3))
    assert service.finalize_batch(batch_id=batch, now=NOW + timedelta(seconds=4)) == ('run',)
    assert len(provider.calls) == 2


def test_resume_after_expired_deadline_reopens_a_full_fetch_window(seeded):
    provider = Provider()
    service = ActivityDetailSyncService(seeded, lambda session: provider, resources=('fit',))
    batch = service.start_batch(user_id='owner', activity_ids=('run',),
                                source_sync_run_id='late-resume', now=NOW)
    service.pause_batch(user_id='owner', batch_id=batch)
    resumed = NOW + timedelta(minutes=5)
    service.resume_batch(user_id='owner', batch_id=batch, now=resumed)
    with seeded() as session:
        deadline = session.get(ActivityDetailBatchModel, batch).deadline_at
        assert deadline >= resumed.replace(tzinfo=None) + timedelta(seconds=120)
        finalizer = session.scalar(select(AgentTaskModel).where(
            AgentTaskModel.idempotency_key == f'activity.detail.finalize.v1:{batch}'))
        assert finalizer.available_at >= deadline
    service.process_resource(fetch_id=_item(seeded, batch).fetch_id,
                             now=resumed + timedelta(seconds=1))
    assert service.finalize_batch(batch_id=batch, now=resumed + timedelta(seconds=2)) == ('run',)


def test_worker_fetches_then_finalizes_without_leaving_processing_tasks(seeded, monkeypatch):
    from scripts import agent_runtime
    provider = Provider()
    service = ActivityDetailSyncService(seeded, lambda session: provider, resources=('fit',))
    batch = service.start_batch(user_id='owner', activity_ids=('run',),
                                source_sync_run_id='worker', now=NOW)
    monkeypatch.setenv('JOHNNY_ACTIVITY_DETAILS_ENABLED', '1')
    monkeypatch.setattr(agent_runtime, '_build_detail_service', lambda session: service, raising=False)
    with seeded() as session:
        assert agent_runtime.work_one(session, now=NOW + timedelta(seconds=1))
        session.commit()
    with seeded() as session:
        assert agent_runtime.work_one(session, now=NOW + timedelta(seconds=2))
        session.commit()
        assert session.get(ActivityDetailBatchModel, batch).status == 'closed'
        assert {task.status for task in session.scalars(select(AgentTaskModel).where(
            AgentTaskModel.correlation_id == batch))} == {'completed'}
    assert len(provider.calls) == 1


def test_recent_unknown_detail_schedules_only_two_late_rechecks(seeded, monkeypatch):
    unknown = NormalizedDetails(activity_id='run', resource='fit', schema_version='test-v1',
        coverage=DetailCoverage(state='unknown', sampling='unknown', limitations=('recording_missing',)))
    provider = Provider([unknown, unknown])
    service = ActivityDetailSyncService(seeded, lambda session: provider, resources=('fit',))
    batch = service.start_batch(user_id='owner', activity_ids=('run',),
                                source_sync_run_id='partial', now=NOW)
    fetch_id = _item(seeded, batch).fetch_id
    service.process_resource(fetch_id=fetch_id, now=NOW + timedelta(seconds=1))
    assert service.finalize_batch(batch_id=batch, now=NOW + timedelta(seconds=2)) == ('run',)
    with seeded() as session:
        tasks = session.scalars(select(AgentTaskModel).where(
            AgentTaskModel.task_type == 'activity.detail.recheck.v1').order_by(
            AgentTaskModel.available_at)).all()
        assert len(tasks) == 2
        assert tasks[0].available_at >= NOW.replace(tzinfo=None) + timedelta(minutes=15)
        assert tasks[1].available_at >= NOW.replace(tzinfo=None) + timedelta(hours=2)
        finalizer = session.scalar(select(AgentTaskModel).where(
            AgentTaskModel.idempotency_key == f'activity.detail.finalize.v1:{batch}'))
        assert finalizer.payload['partial'] is True
        for task in session.scalars(select(AgentTaskModel).where(
                AgentTaskModel.correlation_id == batch,
                AgentTaskModel.task_type != 'activity.detail.recheck.v1')):
            task.status = 'completed'
        session.commit()
    from scripts import agent_runtime
    monkeypatch.setenv('JOHNNY_ACTIVITY_DETAILS_ENABLED', '1')
    monkeypatch.setattr(agent_runtime, '_build_detail_service', lambda session: service, raising=False)
    with seeded() as session:
        assert agent_runtime.work_one(session, now=NOW + timedelta(minutes=16))
        session.commit()
    with seeded() as session:
        recheck = session.scalar(select(ActivityDetailBatchModel.id).where(
            ActivityDetailBatchModel.source_sync_run_id == f'recheck:{batch}:1'))
        assert recheck is not None
    service.process_resource(fetch_id=fetch_id, now=NOW + timedelta(minutes=16, seconds=1))
    service.finalize_batch(batch_id=recheck, now=NOW + timedelta(minutes=16, seconds=2))
    with seeded() as session:
        assert session.scalar(select(func.count()).select_from(AgentTaskModel).where(
            AgentTaskModel.task_type == 'activity.detail.recheck.v1')) == 2


def test_recent_timed_out_fetch_gets_capped_late_rechecks(seeded):
    service = ActivityDetailSyncService(seeded, lambda session: Provider(), resources=('fit',))
    batch = service.start_batch(user_id='owner', activity_ids=('run',),
                                source_sync_run_id='timeout', now=NOW)
    service.finalize_batch(batch_id=batch, now=NOW + timedelta(seconds=120))
    with seeded() as session:
        assert session.scalar(select(func.count()).select_from(AgentTaskModel).where(
            AgentTaskModel.task_type == 'activity.detail.recheck.v1')) == 2


def test_postgresql_two_workers_share_fetch_and_publish_one_changed_batch():
    url = os.getenv('JOHNNY_TEST_DATABASE_URL')
    if not url:
        pytest.skip('disposable PostgreSQL URL not configured')
    parsed = make_url(url)
    if not parsed.drivername.startswith('postgresql') or 'test' not in (parsed.database or ''):
        pytest.fail('concurrent detail test requires a disposable test database')
    engine = create_engine(parsed, pool_size=4)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    suffix = uuid4().hex
    owner, connection, activity = str(uuid4()), str(uuid4()), str(uuid4())
    with factory() as session:
        session.add(UserModel(id=owner, email=f'{suffix}@example.invalid', display_name='Runner'))
        session.flush()
        session.add(IntegrationConnectionModel(id=connection, user_id=owner, provider='garmin_connect'))
        session.flush()
        session.add(ActivityModel(id=activity, user_id=owner, provider_connection_id=connection,
            provider_activity_id=f'provider-{suffix}', started_at=NOW - timedelta(days=1),
            activity_type='running'))
        session.commit()
    entered, release = Event(), Event()

    class SlowProvider(Provider):
        def fetch_activity_detail(self, **kwargs):
            entered.set()
            assert release.wait(5)
            return super().fetch_activity_detail(**kwargs)

    provider = SlowProvider()
    service = ActivityDetailSyncService(factory, lambda session: provider, resources=('fit',))
    manual = service.start_batch(user_id=owner, activity_ids=(activity,),
                                 source_sync_run_id=None, now=NOW)
    backfill = service.start_batch(user_id=owner, activity_ids=(activity,),
                                   source_sync_run_id='backfill', now=NOW)
    fetch_id = _item(factory, manual).fetch_id
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(service.process_resource, fetch_id=fetch_id, now=NOW + timedelta(seconds=1))
            assert entered.wait(5)
            with pytest.raises(ActivityDetailDeferred):
                service.process_resource(fetch_id=fetch_id, now=NOW + timedelta(seconds=2))
            release.set()
            first.result(timeout=5)
        service.process_resource(fetch_id=fetch_id, now=NOW + timedelta(seconds=3))
        assert service.finalize_batch(batch_id=manual, now=NOW + timedelta(seconds=4)) == (activity,)
        assert service.finalize_batch(batch_id=backfill, now=NOW + timedelta(seconds=4)) == ()
        with factory() as session:
            assert session.scalar(select(func.count()).select_from(ActivityDetailSnapshotModel).where(
                ActivityDetailSnapshotModel.activity_id == activity)) == 1
        assert len(provider.calls) == 1
    finally:
        release.set()
        engine.dispose()
