from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select

from src.application.coaching_analysis_evidence import build_coaching_evidence
from src.application.coaching_refresh import CoachingRefreshService
from src.application.interfaces.task_queue import TaskEnvelope
from src.application.training_review_generation import GenerateTrainingReviewHandler
from src.domain.activity_health import DailyHealthMetrics
from src.domain.integrations_notifications import SyncSummary
from src.domain.workout_advice import WorkoutAdviceConstraints
from src.infrastructure.database.activity_repository import SqlAlchemyActivityRepository
from src.infrastructure.database.coaching_analysis_evidence_repository import SqlAlchemyCoachingAnalysisEvidenceRepository
from src.infrastructure.database.coaching_repository import SqlAlchemyCoachingRepository
from src.infrastructure.database.agent_task_queue import SqlAlchemyAgentTaskQueue
from src.infrastructure.database.models import (
    ActivityDetailBatchModel, AgentRunModel, AgentTaskModel, Base,
    CoachingGenerationRequestModel, CoachingInputVersionModel,
    TrainingReviewModel, UserModel,
)


def test_request_merges_same_fingerprint_and_runs_one_successor(sqlite_session_factory):
    from src.application.coaching_generation_requests import CoachingGenerationRequests
    Base.metadata.create_all(sqlite_session_factory.kw['bind'])
    with sqlite_session_factory() as session:
        session.add(UserModel(id='runner', email='runner@example.test', display_name='Runner'))
        session.flush()
        requests = CoachingGenerationRequests(session)
        first = requests.request(user_id='runner', kind='daily_review', slot_id='slot',
                                 fingerprint='a' * 64, reason='detail')
        assert first
        assert requests.request(user_id='runner', kind='daily_review', slot_id='slot',
                                fingerprint='a' * 64, reason='detail') is None
        assert requests.finish(request_id=first, completed_fingerprint='a' * 64) is None
        assert requests.request(user_id='runner', kind='daily_review', slot_id='slot',
                                fingerprint='a' * 64, reason='retry') is None
        second = requests.request(user_id='runner', kind='daily_review', slot_id='slot',
                                  fingerprint='b' * 64, reason='new-detail')
        assert second and second != first
        assert requests.request(user_id='runner', kind='daily_review', slot_id='slot',
                                fingerprint='c' * 64, reason='newer-detail') is None
        successor = requests.finish(request_id=second, completed_fingerprint='b' * 64)
        assert successor and successor != second
        assert requests.finish(request_id=second, completed_fingerprint='b' * 64) is None
        assert requests.finish(request_id=successor, completed_fingerprint='c' * 64) is None


def test_failed_request_releases_slot_and_queues_newer_desired_fingerprint(sqlite_session_factory):
    from src.application.coaching_generation_requests import CoachingGenerationRequests
    Base.metadata.create_all(sqlite_session_factory.kw['bind'])
    with sqlite_session_factory() as session:
        session.add(UserModel(id='runner', email='runner@example.test', display_name='Runner'))
        session.flush()
        requests = CoachingGenerationRequests(session)
        first = requests.request(user_id='runner', kind='daily_review', slot_id='slot',
                                 fingerprint='a' * 64, reason='first')
        requests.request(user_id='runner', kind='daily_review', slot_id='slot',
                         fingerprint='b' * 64, reason='later')
        successor = requests.fail(request_id=first)
        assert successor and successor != first
        assert requests.fail(request_id=first) is None
        assert requests.finish(request_id=successor, completed_fingerprint='b' * 64) is None
        retry = requests.request(user_id='runner', kind='daily_review', slot_id='slot',
                                 fingerprint='c' * 64, reason='new')
        assert retry
        assert requests.fail(request_id=retry) is None
        assert requests.request(user_id='runner', kind='daily_review', slot_id='slot',
                                fingerprint='c' * 64, reason='retry') is not None


def test_five_affected_reviews_queue_only_latest_and_never_advice(sqlite_session_factory):
    Base.metadata.create_all(sqlite_session_factory.kw['bind'])
    today = datetime.now(timezone.utc).date()
    with sqlite_session_factory() as session:
        session.add(UserModel(id='runner', email='runner@example.test', display_name='Runner'))
        session.flush()
        coaching = SqlAlchemyCoachingRepository(session)
        for offset in range(5):
            publication = today - timedelta(days=offset)
            reservation = coaching.reserve_review('runner', publication, 'UTC', f'prior-{offset}')
            assert coaching.publish_review(reservation, {'narrative': f'prior-{offset}'})
        advice = coaching.reserve_advice('runner', today, 'no-workout', 'advice', {})
        assert coaching.publish_advice(advice, {'guidance': 'prior'}, None)
        before_version = session.get(CoachingInputVersionModel, 'runner').revision
        effects = CoachingRefreshService(session).record_change(
            user_id='runner', changed_dates={today - timedelta(days=3)}, today=today,
            reason='detail_batch', affects_advice=False)
        assert len(effects.review_run_ids) == 1
        runs = session.scalars(select(AgentRunModel).where(
            AgentRunModel.user_id == 'runner', AgentRunModel.trigger_type == 'evidence_change')).all()
        assert len(runs) == 1
        affected = session.scalars(select(TrainingReviewModel).where(
            TrainingReviewModel.user_id == 'runner', TrainingReviewModel.freshness == 'stale')).all()
        assert len(affected) == 3
        assert coaching.get_advice_slot('runner', today, 'no-workout')['freshness'] == 'current'
        assert session.get(CoachingInputVersionModel, 'runner').revision == before_version + 1


def test_publication_checks_relevant_manifest_instead_of_global_version(sqlite_session_factory):
    Base.metadata.create_all(sqlite_session_factory.kw['bind'])
    today = datetime.now(timezone.utc).date()
    with sqlite_session_factory() as session:
        session.add(UserModel(id='runner', email='runner@example.test', display_name='Runner'))
        session.flush()
        coaching = SqlAlchemyCoachingRepository(session)
        reservation = coaching.reserve_review('runner', today, 'UTC', 'run-one')
        def bundle():
            return build_coaching_evidence(user_id='runner', kind='daily_review',
                local_date=today, timezone_name='UTC', workout_id=None, constraints=None,
                as_of=datetime.now(timezone.utc),
                store=SqlAlchemyCoachingAnalysisEvidenceRepository(session))
        before = bundle()
        coaching.bump_input_version('runner')  # unrelated global audit revision
        assert coaching.publish_review(reservation, {'narrative': 'review',
            'evidence_manifest': before.manifest, 'evidence_fingerprint': before.fingerprint})
        next_reservation = coaching.reserve_review('runner', today, 'UTC', 'run-two')
        changed_day = today - timedelta(days=1)
        SqlAlchemyActivityRepository(session).save_daily_health_metrics('runner',
            DailyHealthMetrics.create(user_id='runner', metric_date=changed_day,
                                      stress_score=60))
        assert bundle().fingerprint != before.fingerprint
        assert not coaching.publish_review(next_reservation, {'narrative': 'obsolete',
            'evidence_manifest': before.manifest, 'evidence_fingerprint': before.fingerprint})
        assert coaching.get_review_slot('runner', today)['current']['narrative'] == 'review'


def test_same_manifest_is_not_queued_again_while_request_active(sqlite_session_factory):
    Base.metadata.create_all(sqlite_session_factory.kw['bind'])
    today = datetime.now(timezone.utc).date()
    with sqlite_session_factory() as session:
        session.add(UserModel(id='runner', email='runner@example.test', display_name='Runner'))
        session.flush()
        coaching = SqlAlchemyCoachingRepository(session)
        reservation = coaching.reserve_review('runner', today, 'UTC', 'prior')
        assert coaching.publish_review(reservation, {'narrative': 'old'})
        refresh = CoachingRefreshService(session)
        first = refresh.record_change(user_id='runner', changed_dates={today - timedelta(days=1)},
                                      today=today, reason='detail', affects_advice=False)
        second = refresh.record_change(user_id='runner', changed_dates={today - timedelta(days=1)},
                                       today=today, reason='detail', affects_advice=False)
        assert len(first.review_run_ids) == 1
        assert second.review_run_ids == ()


def test_review_generation_persists_manifest_and_reuses_unchanged_revision(sqlite_session_factory):
    Base.metadata.create_all(sqlite_session_factory.kw['bind'])
    today = datetime.now(timezone.utc).date()
    with sqlite_session_factory() as session:
        session.add(UserModel(id='runner', email='runner@example.test', display_name='Runner'))
        session.flush()
        coaching = SqlAlchemyCoachingRepository(session)
        handler = GenerateTrainingReviewHandler(coaching=coaching, evidence=coaching)
        before_version = session.get(CoachingInputVersionModel, 'runner')
        before_revision = before_version.revision if before_version else 0
        first = handler.handle(user_id='runner', publication_date=today,
                               timezone_name='UTC', run_id='run-one')
        assert first['evidence_manifest']['kind'] == 'daily_review'
        assert first['evidence_fingerprint'] == build_coaching_evidence(
            user_id='runner', kind='daily_review', local_date=today, timezone_name='UTC',
            workout_id=None, constraints=None, as_of=datetime.now(timezone.utc),
            store=SqlAlchemyCoachingAnalysisEvidenceRepository(session)).fingerprint
        first_id = coaching.get_review_slot('runner', today)['revision_id']
        handler.handle(user_id='runner', publication_date=today,
                       timezone_name='UTC', run_id='run-two')
        assert coaching.get_review_slot('runner', today)['revision_id'] == first_id
        assert session.get(CoachingInputVersionModel, 'runner').revision == before_revision


def test_new_manifest_during_active_run_queues_at_most_one_successor(sqlite_session_factory):
    Base.metadata.create_all(sqlite_session_factory.kw['bind'])
    today = datetime.now(timezone.utc).date()
    yesterday = today - timedelta(days=1)
    with sqlite_session_factory() as session:
        session.add(UserModel(id='runner', email='runner@example.test', display_name='Runner'))
        session.flush()
        coaching = SqlAlchemyCoachingRepository(session)
        prior = coaching.reserve_review('runner', today, 'UTC', 'prior')
        assert coaching.publish_review(prior, {'narrative': 'prior'})
        refresh = CoachingRefreshService(session)
        first = refresh.record_change(user_id='runner', changed_dates={yesterday}, today=today,
                                      reason='detail', affects_advice=False)
        row = session.scalar(select(CoachingGenerationRequestModel))
        first_request_id, first_fingerprint = row.active_request_id, row.active_fingerprint
        assert len(first.review_run_ids) == 1
        SqlAlchemyActivityRepository(session).save_daily_health_metrics('runner',
            DailyHealthMetrics.create(user_id='runner', metric_date=yesterday, stress_score=65))
        second = refresh.record_change(user_id='runner', changed_dates={yesterday}, today=today,
                                       reason='detail', affects_advice=False)
        assert second.review_run_ids == ()
        assert row.desired_fingerprint != first_fingerprint
        successor_run = refresh.finish_review_request(first_request_id, first_fingerprint)
        assert successor_run
        assert refresh.finish_review_request(first_request_id, first_fingerprint) is None
        assert session.scalar(select(CoachingGenerationRequestModel)).active_run_id == successor_run
        assert len(session.scalars(select(AgentRunModel).where(
            AgentRunModel.trigger_type == 'evidence_change')).all()) == 2


def test_summary_sync_waits_for_three_resource_detail_batch(sqlite_session_factory):
    Base.metadata.create_all(sqlite_session_factory.kw['bind'])
    now = datetime.now(timezone.utc)
    today = now.date()
    yesterday = today - timedelta(days=1)
    with sqlite_session_factory() as session:
        session.add(UserModel(id='runner', email='runner@example.test', display_name='Runner'))
        session.flush()
        coaching = SqlAlchemyCoachingRepository(session)
        for offset in range(3):
            reservation = coaching.reserve_review('runner', today - timedelta(days=offset),
                                                  'UTC', f'prior-{offset}')
            assert coaching.publish_review(reservation, {'narrative': 'old'})
        batch = ActivityDetailBatchModel(id='batch', user_id='runner',
            source_sync_run_id='sync-1', status='pending', deadline_at=now + timedelta(minutes=2))
        session.add(batch)
        SqlAlchemyAgentTaskQueue(session).enqueue(TaskEnvelope(
            task_type='activity.detail.finalize.v1', payload={'batch_id': 'batch'},
            correlation_id='batch', idempotency_key='activity.detail.finalize.v1:batch'))
        summary = SyncSummary.from_payload({'resources': {
            'activities': {'stored': 1}, 'fit': {'stored': 1},
            'splits': {'stored': 1}, 'details': {'stored': 1}},
            'stored_dates': {name: [yesterday.isoformat()]
                             for name in ('activities', 'fit', 'splits', 'details')}})
        refresh = CoachingRefreshService(session)
        early = refresh.record_sync(user_id='runner', summary=summary, today=today,
                                    timezone_name='UTC', source_sync_run_id='sync-1')
        assert early.review_run_ids == ()
        assert coaching.get_review_slot('runner', today)['freshness'] == 'stale'
        finalizer = session.scalar(select(AgentTaskModel).where(
            AgentTaskModel.idempotency_key == 'activity.detail.finalize.v1:batch'))
        assert finalizer.payload['coaching_changed_dates'] == [yesterday.isoformat()]
        batch.status = 'closed'
        finished = refresh.complete_detail_batch(batch_id='batch', changed_activity_ids=(), now=now)
        assert len(finished.review_run_ids) == 1
        assert refresh.complete_detail_batch(batch_id='batch', changed_activity_ids=(), now=now).review_run_ids == ()


def test_unrelated_old_evidence_leaves_current_advice_fresh(sqlite_session_factory):
    Base.metadata.create_all(sqlite_session_factory.kw['bind'])
    today = datetime.now(timezone.utc).date()
    with sqlite_session_factory() as session:
        session.add(UserModel(id='runner', email='runner@example.test', display_name='Runner'))
        session.flush()
        coaching = SqlAlchemyCoachingRepository(session)
        reservation = coaching.reserve_advice('runner', today, 'no-workout', 'advice', {})
        bundle = build_coaching_evidence(user_id='runner', kind='workout_advice',
            local_date=today, timezone_name='UTC', workout_id=None,
            constraints=WorkoutAdviceConstraints(), as_of=datetime.now(timezone.utc),
            store=SqlAlchemyCoachingAnalysisEvidenceRepository(session))
        assert coaching.publish_advice(reservation, {
            'advice_date': today.isoformat(), 'timezone_name': 'UTC', 'workout_id': None,
            'constraints': {'available_minutes': None, 'feeling': 'usual',
                            'cannot_train_today': False},
            'guidance': 'rest', 'evidence_manifest': bundle.manifest,
            'evidence_fingerprint': bundle.fingerprint}, None)
        effects = CoachingRefreshService(session).record_change(
            user_id='runner', changed_dates={today - timedelta(days=40)},
            today=today, reason='old_detail')
        assert effects.invalidated_advice_ids == ()
        assert coaching.get_advice_slot('runner', today, 'no-workout')['freshness'] == 'current'
