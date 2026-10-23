"""Release gates for coaching detail task contracts and safe cutover."""

from datetime import datetime, timedelta, timezone
import json
import os
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from scripts.agent_runtime import work_one
from src.application.activity_detail_sync import ActivityDetailSyncService
from src.application.coaching_analysis_generation import coaching_analysis_v2_enabled
from src.application.coaching_analysis_generation import generate_coaching_analysis
from src.application.coaching_refresh import CoachingRefreshService
from src.application.training_review_generation import GenerateTrainingReviewHandler
from src.domain.agent_runtime import ModelResponse, TokenUsage
from src.domain.activity_details import ActivitySampleChunk, DetailCoverage, NormalizedDetails
from src.main import create_app
from src.application.interfaces.task_queue import TaskEnvelope
from src.infrastructure.database.agent_task_queue import SqlAlchemyAgentTaskQueue
from src.infrastructure.database.coaching_repository import SqlAlchemyCoachingRepository
from src.infrastructure.database.models import (
    ActivityDetailBatchItemModel, ActivityDetailFetchModel,
    ActivityDetailSnapshotModel, ActivityModel,
    AgentRunModel, AgentTaskModel, Base, CoachingGenerationRequestModel,
    IntegrationConnectionModel, TrainingReviewModel, TrainingReviewRevisionModel,
    UserModel, WorkoutAdviceRevisionModel,
)


NOW = datetime(2027, 1, 16, 8, tzinfo=timezone.utc)


def test_worker_claims_supported_legacy_and_v1_but_leaves_unknown_contract_observable(
    sqlite_session_factory,
):
    """An unsupported task must not block an older compatible task or be executed."""
    Base.metadata.create_all(sqlite_session_factory.kw['bind'])
    with sqlite_session_factory() as session:
        queue = SqlAlchemyAgentTaskQueue(session)
        unknown = queue.enqueue(TaskEnvelope(task_type='training-plan.daily-check',
            payload={'anchor_date': '2027-01-16', 'contract_version': 2},
            idempotency_key='unknown-contract', available_at=NOW))
        legacy = queue.enqueue(TaskEnvelope(task_type='training-plan.daily-check',
            payload={'anchor_date': '2027-01-16'},
            idempotency_key='legacy-contract', available_at=NOW + timedelta(seconds=1)))
        session.get(AgentTaskModel, legacy.id).payload = {'anchor_date': '2027-01-16'}
        versioned = queue.enqueue(TaskEnvelope(task_type='training-plan.daily-check',
            payload={'anchor_date': '2027-01-16', 'contract_version': 1},
            idempotency_key='current-contract', available_at=NOW + timedelta(seconds=2)))
        session.commit()

    with sqlite_session_factory() as session:
        queue = SqlAlchemyAgentTaskQueue(session)
        first = queue.claim_next(now=NOW + timedelta(seconds=3),
                                 claim_timeout=timedelta(minutes=5),
                                 supported_contracts={'training-plan.daily-check': (0, 1)})
        assert first is not None and first.id == legacy.id
        queue.complete(first.id, now=NOW + timedelta(seconds=3))
        second = queue.claim_next(now=NOW + timedelta(seconds=3),
                                  claim_timeout=timedelta(minutes=5),
                                  supported_contracts={'training-plan.daily-check': (0, 1)})
        assert second is not None and second.id == versioned.id
        queue.complete(second.id, now=NOW + timedelta(seconds=3))
        assert queue.claim_next(now=NOW + timedelta(seconds=3),
                                claim_timeout=timedelta(minutes=5),
                                supported_contracts={'training-plan.daily-check': (0, 1)}) is None
        assert session.get(AgentTaskModel, unknown.id).status == 'queued'


def test_new_tasks_carry_v1_contract_and_worker_does_not_claim_unknown_versions(
    sqlite_session_factory,
):
    Base.metadata.create_all(sqlite_session_factory.kw['bind'])
    with sqlite_session_factory() as session:
        queue = SqlAlchemyAgentTaskQueue(session)
        current = queue.enqueue(TaskEnvelope(task_type='training-plan.daily-check',
            payload={'anchor_date': '2027-01-16'},
            idempotency_key='current', available_at=NOW))
        unknown = queue.enqueue(TaskEnvelope(task_type='training-plan.daily-check',
            payload={'anchor_date': '2027-01-16', 'contract_version': 99},
            idempotency_key='future', available_at=NOW))
        invalid_null = queue.enqueue(TaskEnvelope(task_type='training-plan.daily-check',
            payload={'anchor_date': '2027-01-16', 'contract_version': None},
            idempotency_key='null-version', available_at=NOW))
        session.commit()
    assert current.payload['contract_version'] == 1
    with sqlite_session_factory() as session:
        assert work_one(session, now=NOW)
        session.commit()
        assert session.get(AgentTaskModel, current.id).status == 'completed'
        assert not work_one(session, now=NOW)
        assert session.get(AgentTaskModel, unknown.id).status == 'queued'
        assert session.get(AgentTaskModel, invalid_null.id).status == 'queued'


def test_health_reports_build_and_supported_worker_contract_without_secrets(monkeypatch):
    monkeypatch.setenv('JOHNNY_BUILD_SHA', 'a' * 40)
    response = TestClient(create_app()).get('/ready')
    assert response.status_code == 200
    assert response.json()['worker_contract'] == {'build': 'a' * 40,
                                                   'versions': [0, 1]}
    assert 'DATABASE_URL' not in str(response.json())


def test_flags_off_defer_detail_work_and_keep_legacy_advice_readable(
    sqlite_session_factory, monkeypatch,
):
    monkeypatch.setenv('JOHNNY_ACTIVITY_DETAILS_ENABLED', 'false')
    monkeypatch.setenv('JOHNNY_COACHING_ANALYSIS_V2_ENABLED', 'false')
    Base.metadata.create_all(sqlite_session_factory.kw['bind'])
    with sqlite_session_factory() as session:
        session.add(UserModel(id='legacy-runner', email='legacy@example.test',
                              display_name='Runner'))
        session.flush()
        coaching = SqlAlchemyCoachingRepository(session)
        advice = coaching.reserve_advice('legacy-runner', NOW.date(), 'no-workout',
                                         'legacy-run', {})
        assert coaching.publish_advice(advice, {'guidance': 'Keep it easy.'}, None)
        queued = SqlAlchemyAgentTaskQueue(session).enqueue(TaskEnvelope(
            task_type='activity.detail.fetch.v1', payload={'fetch_id': 'not-fetched'},
            idempotency_key='detail-paused', available_at=NOW))
        session.commit()
    with sqlite_session_factory() as session:
        assert not coaching_analysis_v2_enabled()
        assert work_one(session, now=NOW)
        session.commit()
        task = session.get(AgentTaskModel, queued.id)
        assert task.status == 'queued'
        assert task.available_at.replace(tzinfo=timezone.utc) == NOW + timedelta(hours=1)
        slot = SqlAlchemyCoachingRepository(session).get_advice_slot(
            'legacy-runner', NOW.date(), 'no-workout')
        assert slot['current']['guidance'] == 'Keep it easy.'


def _exercise_five_review_slots_three_resources_replay_and_late_change_coalesce(engine):
    """A replayed batch must keep immutable history and queue only one successor."""
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    activity_day = NOW.date() - timedelta(days=5)

    class Provider:
        revision = 1
        calls = 0

        def fetch_activity_detail(self, *, connection, activity_id, resource,
                                  provider_activity_id):
            assert (connection.id, activity_id, provider_activity_id) == (
                'connection', 'run', 'provider-run')
            self.calls += 1
            return NormalizedDetails(activity_id=activity_id, resource=resource,
                schema_version='acceptance-v1',
                coverage=DetailCoverage(state='complete', sampling='recorded'),
                sample_chunks=(ActivitySampleChunk(ordinal=0,
                    samples=({'elapsed_seconds': self.revision, 'channel': resource},)),))

    provider = Provider()
    class Gateway:
        calls = 0

        def complete(self, _request):
            self.calls += 1
            return ModelResponse(content=json.dumps({
                'headline': '先按現有資料執行', 'summary': '分段資料已納入回顧。',
                'findings': [{'observation': '有活動資料。',
                              'interpretation': '可檢視分段證據。',
                              'evidence_refs': ['evidence:window']}],
                'actions': [{'action_id': 'inspect_evidence', 'text': '檢視證據。',
                             'evidence_refs': ['evidence:window']}],
                'limitations': [], 'evidence_refs': ['evidence:window'],
            }, ensure_ascii=False), provider='openai', model='acceptance-model',
                token_usage=TokenUsage(input_tokens=10, output_tokens=10))

    gateway = Gateway()
    service = ActivityDetailSyncService(factory, lambda _session: provider,
                                        resources=('fit', 'splits', 'details'))
    try:
        with factory() as session:
            session.add(UserModel(id='runner', email='runner@example.test',
                                  display_name='Runner'))
            session.flush()
            session.add(IntegrationConnectionModel(id='connection', user_id='runner',
                                                    provider='garmin_connect'))
            session.flush()
            session.add(ActivityModel(id='run', user_id='runner',
                provider_connection_id='connection', provider_activity_id='provider-run',
                started_at=NOW - timedelta(days=5), activity_type='running',
                duration_seconds=2100, distance_meters=5000))
            coaching = SqlAlchemyCoachingRepository(session)
            for offset in range(5):
                publication = NOW.date() - timedelta(days=offset)
                reservation = coaching.reserve_review('runner', publication, 'UTC',
                                                      f'old-{offset}')
                assert coaching.publish_review(reservation,
                                               {'narrative': f'old-{offset}'})
            advice = coaching.reserve_advice('runner', NOW.date(), 'no-workout',
                                             'user-requested-advice', {})
            assert coaching.publish_advice(advice, {'guidance': 'existing advice'}, None)
            session.commit()

        batch = service.start_batch(user_id='runner', activity_ids=('run',),
                                    source_sync_run_id='initial-sync', now=NOW)
        with factory() as session:
            items = session.scalars(select(ActivityDetailBatchItemModel).where(
                ActivityDetailBatchItemModel.batch_id == batch)).all()
        assert len(items) == 3
        service.process_resource(fetch_id=items[0].fetch_id, now=NOW)
        service.process_resource(fetch_id=items[0].fetch_id, now=NOW + timedelta(seconds=1))
        for item in items[1:]:
            service.process_resource(fetch_id=item.fetch_id, now=NOW + timedelta(seconds=2))
        assert service.finalize_batch(batch_id=batch, now=NOW + timedelta(seconds=3)) == ('run',)
        assert service.finalize_batch(batch_id=batch, now=NOW + timedelta(seconds=4)) == ()
        with factory() as session:
            assert session.scalar(select(func.count()).select_from(
                ActivityDetailSnapshotModel)) == 3
            refresh = CoachingRefreshService(session)
            first = refresh.record_change(user_id='runner', changed_dates={activity_day},
                today=NOW.date(), reason='detail_batch', affects_advice=False, as_of=NOW)
            assert len(first.review_run_ids) == 1
            generated = GenerateTrainingReviewHandler(
                coaching=SqlAlchemyCoachingRepository(session),
                evidence=SqlAlchemyCoachingRepository(session), gateway=gateway,
                analysis_generator=generate_coaching_analysis, now=lambda: NOW).handle(
                    user_id='runner', publication_date=NOW.date(), timezone_name='UTC',
                    run_id=first.review_run_ids[0])
            assert generated['analysis']['analysis_mode'] == 'llm'
            initial_model_calls = gateway.calls
            assert initial_model_calls == 1
            assert refresh.record_change(user_id='runner', changed_dates={activity_day},
                today=NOW.date(), reason='replay', affects_advice=False,
                as_of=NOW).review_run_ids == ()
            assert gateway.calls == initial_model_calls
            assert session.scalar(select(func.count()).select_from(
                TrainingReviewModel).where(TrainingReviewModel.freshness == 'stale')) == 4
            assert session.scalar(select(func.count()).select_from(
                TrainingReviewRevisionModel)) == 6
            assert session.scalar(select(func.count()).select_from(
                WorkoutAdviceRevisionModel)) == 1
            request = session.scalar(select(CoachingGenerationRequestModel))
            first_request_id = request.active_request_id
            first_fingerprint = request.active_fingerprint
            session.commit()

        provider.revision = 2
        late_batch = service.start_batch(user_id='runner', activity_ids=('run',),
            source_sync_run_id='late-sync', now=NOW + timedelta(minutes=1))
        with factory() as session:
            late_items = session.scalars(select(ActivityDetailBatchItemModel).where(
                ActivityDetailBatchItemModel.batch_id == late_batch)).all()
        for item in late_items:
            service.process_resource(fetch_id=item.fetch_id, now=NOW + timedelta(minutes=1, seconds=1))
        assert service.finalize_batch(batch_id=late_batch,
            now=NOW + timedelta(minutes=1, seconds=2)) == ('run',)
        with factory() as session:
            refresh = CoachingRefreshService(session)
            late = refresh.record_change(user_id='runner', changed_dates={activity_day},
                today=NOW.date(), reason='late_detail', affects_advice=False,
                as_of=NOW + timedelta(minutes=1))
            assert late.review_run_ids == ()
            request = session.scalar(select(CoachingGenerationRequestModel))
            assert request.desired_fingerprint != first_fingerprint
            successor = refresh.finish_review_request(first_request_id, first_fingerprint)
            assert successor
            assert refresh.finish_review_request(first_request_id, first_fingerprint) is None
            assert session.scalar(select(func.count()).select_from(AgentRunModel).where(
                AgentRunModel.trigger_type == 'evidence_change')) == 2
            assert session.scalar(select(func.count()).select_from(
                TrainingReviewRevisionModel)) == 6
            assert session.scalar(select(func.count()).select_from(
                WorkoutAdviceRevisionModel)) == 1
            assert session.scalar(select(func.count()).select_from(
                ActivityDetailSnapshotModel)) == 6
            assert gateway.calls == initial_model_calls
            session.commit()
        replay_batch = service.start_batch(user_id='runner', activity_ids=('run',),
            source_sync_run_id='identical-replay', now=NOW + timedelta(minutes=2))
        with factory() as session:
            replay_items = session.scalars(select(ActivityDetailBatchItemModel).where(
                ActivityDetailBatchItemModel.batch_id == replay_batch)).all()
        for item in replay_items:
            service.process_resource(fetch_id=item.fetch_id,
                now=NOW + timedelta(minutes=2, seconds=1))
        assert service.finalize_batch(batch_id=replay_batch,
            now=NOW + timedelta(minutes=2, seconds=2)) == ()
        with factory() as session:
            assert CoachingRefreshService(session).record_change(
                user_id='runner', changed_dates={activity_day}, today=NOW.date(),
                reason='identical_replay', affects_advice=False,
                as_of=NOW + timedelta(minutes=2)).review_run_ids == ()
            assert session.scalar(select(func.count()).select_from(
                ActivityDetailSnapshotModel)) == 6
            assert session.scalar(select(func.count()).select_from(
                TrainingReviewRevisionModel)) == 6
            fetches = session.scalars(select(ActivityDetailFetchModel)).all()
            assert len(fetches) == 3
            assert all(fetch.status == 'available' and fetch.retry_count == 0
                       for fetch in fetches)
            assert gateway.calls == initial_model_calls
        assert provider.calls == 9
    finally:
        engine.dispose()


def test_five_review_slots_three_resources_replay_and_late_change_coalesce(tmp_path):
    _exercise_five_review_slots_three_resources_replay_and_late_change_coalesce(
        create_engine(f"sqlite:///{tmp_path / 'release-acceptance.db'}"))


def test_postgresql_five_review_slots_replay_and_late_change_coalesce():
    test_url = os.getenv('JOHNNY_TEST_DATABASE_URL')
    if not test_url:
        pytest.skip('JOHNNY_TEST_DATABASE_URL is not configured')
    parsed = make_url(test_url)
    if not parsed.drivername.startswith('postgresql') or 'test' not in (parsed.database or ''):
        pytest.fail('acceptance test requires a disposable PostgreSQL test database')
    schema = f'coaching_acceptance_{uuid4().hex[:12]}'
    admin = create_engine(test_url)
    with admin.begin() as connection:
        connection.exec_driver_sql(f'CREATE SCHEMA {schema}')
    try:
        schema_url = parsed.update_query_dict({'options': f'-csearch_path={schema}'})
        _exercise_five_review_slots_three_resources_replay_and_late_change_coalesce(
            create_engine(schema_url))
    finally:
        with admin.begin() as connection:
            connection.exec_driver_sql(f'DROP SCHEMA {schema} CASCADE')
        admin.dispose()


def test_postgresql_claim_ignores_malformed_future_contract():
    test_url = os.getenv('JOHNNY_TEST_DATABASE_URL')
    if not test_url:
        pytest.skip('JOHNNY_TEST_DATABASE_URL is not configured')
    parsed = make_url(test_url)
    if not parsed.drivername.startswith('postgresql') or 'test' not in (parsed.database or ''):
        pytest.fail('claim test requires a disposable PostgreSQL test database')
    engine = create_engine(test_url)
    try:
        with sessionmaker(bind=engine, expire_on_commit=False)() as session:
            queue = SqlAlchemyAgentTaskQueue(session)
            token = uuid4().hex
            queue.enqueue(TaskEnvelope(task_type='training-plan.daily-check',
                payload={'contract_version': 'future', 'anchor_date': '2027-01-16'},
                idempotency_key=f'{token}:unsupported', available_at=NOW))
            queue.enqueue(TaskEnvelope(task_type='training-plan.daily-check',
                payload={'contract_version': None, 'anchor_date': '2027-01-16'},
                idempotency_key=f'{token}:null', available_at=NOW))
            supported = queue.enqueue(TaskEnvelope(task_type='training-plan.daily-check',
                payload={'anchor_date': '2027-01-16'},
                idempotency_key=f'{token}:supported', available_at=NOW))
            claimed = queue.claim_next(now=NOW, claim_timeout=timedelta(minutes=5),
                supported_contracts={'training-plan.daily-check': (0, 1)})
            assert claimed is not None and claimed.id == supported.id
            session.rollback()
    finally:
        engine.dispose()
