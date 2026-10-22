"""Versioned activity evidence must survive retries and stay with its owner."""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import Session

from src.domain.activity_details import ActivitySampleChunk, ActivitySegment, DetailCoverage, NormalizedDetails
from src.infrastructure.database.activity_detail_repository import SqlAlchemyActivityDetailRepository
from src.infrastructure.database.models import (
    ActivityModel, Base, IntegrationConnectionModel, UserModel,
    ActivityDetailSnapshotModel, ActivitySegmentModel, ActivitySampleChunkModel,
)

NOW = datetime(2026, 10, 22, 10, tzinfo=timezone.utc)


@pytest.fixture
def seeded(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'detail.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add_all([
            UserModel(id='owner-a', email='a@example.invalid', display_name='A'),
            UserModel(id='owner-b', email='b@example.invalid', display_name='B'),
        ])
        session.flush()
        session.add_all([
            IntegrationConnectionModel(id='conn-a', user_id='owner-a', provider='garmin_connect'),
            IntegrationConnectionModel(id='conn-b', user_id='owner-b', provider='garmin_connect'),
        ])
        session.flush()
        session.add_all([
            ActivityModel(id='activity-a', user_id='owner-a', provider_connection_id='conn-a',
                          provider_activity_id='same-provider-id', started_at=NOW, activity_type='running',
                          duration_seconds=600, provider_summary={'match_reviewed': True, 'matched_workout_id': 'plan-a'}),
            ActivityModel(id='activity-b', user_id='owner-b', provider_connection_id='conn-b',
                          provider_activity_id='same-provider-id', started_at=NOW, activity_type='running'),
            ActivityModel(id='manual', user_id='owner-a', provider_connection_id=None,
                          provider_activity_id=None, started_at=NOW, activity_type='running'),
        ])
        session.commit()
    yield engine
    engine.dispose()


def details(activity_id='activity-a', distance=1000.0, resource='splits'):
    return NormalizedDetails(
        activity_id=activity_id, resource=resource, schema_version='garmin-v1',
        coverage=DetailCoverage(state='complete', sampling='recorded', covered_seconds=600),
        segments=(ActivitySegment(source_index=0, source_kind='lap', start_at=NOW,
                                  end_at=NOW + timedelta(minutes=10), timer_seconds=600,
                                  elapsed_seconds=600, distance_meters=distance),),
        sample_chunks=(ActivitySampleChunk(ordinal=0, samples=({'elapsed_seconds': 0, 'heart_rate_bpm': 120},)),),
        source_payload={'lapDTOs': [{'duration': 600, 'distance': distance}]},
    )


def test_same_evidence_retry_keeps_snapshot_and_children(seeded):
    with Session(seeded) as session:
        repo = SqlAlchemyActivityDetailRepository(session)
        first = repo.save_snapshot(user_id='owner-a', details=details(), fetched_at=NOW)
        second = repo.save_snapshot(user_id='owner-a', details=details(), fetched_at=NOW + timedelta(hours=1))
        assert second.id == first.id
        assert second.fetched_at == NOW
        assert session.scalar(select(func.count()).select_from(ActivityDetailSnapshotModel)) == 1
        assert session.scalar(select(func.count()).select_from(ActivitySegmentModel)) == 1
        assert session.scalar(select(func.count()).select_from(ActivitySampleChunkModel)) == 1
        assert repo.get_snapshots('owner-a', 'activity-a') == (first,)


def test_changed_content_creates_immutable_revision_and_updates_current_pointer(seeded):
    with Session(seeded) as session:
        repo = SqlAlchemyActivityDetailRepository(session)
        first = repo.save_snapshot(user_id='owner-a', details=details(), fetched_at=NOW)
        changed = repo.save_snapshot(user_id='owner-a', details=details(distance=1100),
                                     fetched_at=NOW + timedelta(hours=1))
        assert changed.id != first.id
        assert first.segments[0].distance_meters == 1000
        assert [s.segments[0].distance_meters for s in repo.get_snapshots('owner-a', 'activity-a')] == [1000, 1100]
        assert repo.get_fetch('owner-a', 'activity-a', 'splits').current_snapshot_id == changed.id
        assert repo.get_fetch('owner-a', 'activity-a', 'splits').last_successful_sync_at == NOW + timedelta(hours=1)


def test_late_completion_of_older_fetch_does_not_replace_newer_evidence(seeded):
    with Session(seeded) as session:
        repo = SqlAlchemyActivityDetailRepository(session)
        current = repo.save_snapshot(user_id='owner-a', details=details(distance=1100),
                                     fetched_at=NOW + timedelta(hours=1))
        repo.save_snapshot(user_id='owner-a', details=details(distance=1000), fetched_at=NOW)
        fetch = repo.get_fetch('owner-a', 'activity-a', 'splits')
        assert fetch.current_snapshot_id == current.id
        assert fetch.last_successful_sync_at == NOW + timedelta(hours=1)


def test_identical_provider_ids_on_other_connections_remain_separate(seeded):
    with Session(seeded) as session:
        repo = SqlAlchemyActivityDetailRepository(session)
        a = repo.save_snapshot(user_id='owner-a', details=details('activity-a'), fetched_at=NOW)
        b = repo.save_snapshot(user_id='owner-b', details=details('activity-b'), fetched_at=NOW)
        assert a.id != b.id
        assert repo.get_snapshots('owner-a', 'activity-b') == ()
        assert repo.get_snapshots('owner-b', 'activity-a') == ()
        assert repo.get_fetch('owner-b', 'activity-a', 'splits') is None
        assert repo.get_snapshots('owner-a', 'activity-a') == (a,)


def test_foreign_or_manual_activity_cannot_be_enriched(seeded):
    with Session(seeded) as session:
        repo = SqlAlchemyActivityDetailRepository(session)
        with pytest.raises(ValueError, match='owned provider activity'):
            repo.save_snapshot(user_id='owner-b', details=details('activity-a'), fetched_at=NOW)
        with pytest.raises(ValueError, match='owned provider activity'):
            repo.save_snapshot(user_id='owner-a', details=details('manual'), fetched_at=NOW)
        assert session.scalar(select(func.count()).select_from(ActivityDetailSnapshotModel)) == 0


def test_sensitive_source_fields_are_not_persisted(seeded):
    with Session(seeded) as session:
        repo = SqlAlchemyActivityDetailRepository(session)
        unsafe = NormalizedDetails(activity_id='activity-a', resource='details', schema_version='v1',
            coverage=DetailCoverage(state='partial', sampling='chart'),
            source_payload={'activityDetailMetrics': [{'heart_rate': 120, 'latitude': 23.1}]})
        with pytest.raises(ValueError, match='sensitive'):
            repo.save_snapshot(user_id='owner-a', details=unsafe, fetched_at=NOW)
        named = NormalizedDetails(activity_id='activity-a', resource='details', schema_version='v1',
            coverage=DetailCoverage(state='partial', sampling='chart'),
            source_payload={'activityName': 'Private route', 'athleteEmail': 'runner@example.invalid'})
        with pytest.raises(ValueError, match='sensitive'):
            repo.save_snapshot(user_id='owner-a', details=named, fetched_at=NOW)
        assert session.scalar(select(func.count()).select_from(ActivityDetailSnapshotModel)) == 0


def test_raw_sample_series_cannot_be_duplicated_in_source_payload(seeded):
    with Session(seeded) as session:
        repo = SqlAlchemyActivityDetailRepository(session)
        duplicated = NormalizedDetails(activity_id='activity-a', resource='details', schema_version='v1',
            coverage=DetailCoverage(state='partial', sampling='chart'),
            sample_chunks=(ActivitySampleChunk(ordinal=0, samples=({'heart_rate_bpm': 120},)),),
            source_payload={'recordSamples': [{'heart_rate_bpm': 120}]})
        with pytest.raises(ValueError, match='raw sample'):
            repo.save_snapshot(user_id='owner-a', details=duplicated, fetched_at=NOW)


def test_analysis_reuses_fingerprint_and_rejects_foreign_snapshots(seeded):
    with Session(seeded) as session:
        repo = SqlAlchemyActivityDetailRepository(session)
        foreign = repo.save_snapshot(user_id='owner-b', details=details('activity-b'), fetched_at=NOW)
        class Analysis:
            activity_id = 'activity-a'
            fingerprint = 'analysis-hash'
            algorithm_version = 'execution-analysis-v1'
            prescription_revision_id = None
            snapshot_ids = (foreign.id,)
            def to_payload(self):
                return {'finding': 'fact-1'}
        with pytest.raises(ValueError, match='snapshot ownership'):
            repo.save_analysis('owner-a', Analysis())
        own = repo.save_snapshot(user_id='owner-a', details=details(), fetched_at=NOW)
        Analysis.snapshot_ids = (own.id,)
        first = repo.save_analysis('owner-a', Analysis())
        assert repo.save_analysis('owner-a', Analysis()) == first


def test_analysis_rejects_snapshot_from_another_activity_of_same_owner(seeded):
    with Session(seeded) as session:
        session.add(ActivityModel(id='activity-a2', user_id='owner-a', provider_connection_id='conn-a',
                                  provider_activity_id='other-provider-id', started_at=NOW,
                                  activity_type='running'))
        session.flush()
        repo = SqlAlchemyActivityDetailRepository(session)
        other = repo.save_snapshot(user_id='owner-a', details=details('activity-a2'), fetched_at=NOW)
        class Analysis:
            activity_id = 'activity-a'
            fingerprint = 'cross-activity-analysis'
            algorithm_version = 'execution-analysis-v1'
            prescription_revision_id = None
            snapshot_ids = (other.id,)
            def to_payload(self):
                return {'finding': 'not applicable'}
        with pytest.raises(ValueError, match='snapshot ownership'):
            repo.save_analysis('owner-a', Analysis())


def test_analysis_fingerprint_cannot_alias_another_activity(seeded):
    with Session(seeded) as session:
        session.add(ActivityModel(id='activity-a2', user_id='owner-a', provider_connection_id='conn-a',
                                  provider_activity_id='other-provider-id', started_at=NOW,
                                  activity_type='running'))
        session.flush()
        repo = SqlAlchemyActivityDetailRepository(session)
        first = repo.save_snapshot(user_id='owner-a', details=details('activity-a'), fetched_at=NOW)
        second = repo.save_snapshot(user_id='owner-a', details=details('activity-a2'), fetched_at=NOW)
        class Analysis:
            activity_id = 'activity-a'
            fingerprint = 'same-fingerprint'
            algorithm_version = 'execution-analysis-v1'
            prescription_revision_id = None
            snapshot_ids = (first.id,)
            def to_payload(self):
                return {'finding': 'distinct'}
        repo.save_analysis('owner-a', Analysis())
        Analysis.activity_id = 'activity-a2'
        Analysis.snapshot_ids = (second.id,)
        with pytest.raises(ValueError, match='fingerprint collision'):
            repo.save_analysis('owner-a', Analysis())
