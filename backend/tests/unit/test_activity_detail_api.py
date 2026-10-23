"""Owner-scoped, summary-only activity evidence APIs."""

from datetime import datetime, timedelta, timezone

from src.api.dependencies import CurrentUser, get_session, ensure_current_user
from src.infrastructure.database.models import (
    ActivityDetailFetchModel, ActivityDetailSnapshotModel, ActivityExecutionAnalysisModel,
    ActivityModel, ActivitySampleChunkModel, ActivitySegmentModel, IntegrationConnectionModel,
)
from tests.unit.api_test_helpers import create_sqlite_test_client


HEADERS = {'X-Johnny-User-Id': 'detail-owner'}
NOW = datetime(2027, 1, 15, 12, tzinfo=timezone.utc)


def _analysis(activity_id, snapshot_id, *, fingerprint):
    return {'activity_id': activity_id, 'activity_ids': [activity_id],
        'fingerprint': fingerprint, 'prescription_revision_id': None,
        'snapshot_ids': [snapshot_id], 'mapping': 'estimated',
        'facts': [{'id': 'f1', 'metric': 'actual_duration_seconds', 'value': 2100,
                   'unit': 's', 'scope': 'session', 'evidence_refs': [snapshot_id],
                   'denominator_seconds': None, 'covered_seconds': None}],
        'findings': [{'code': 'limited_detail', 'fact_ids': ['f1'],
                      'supports': '可讀取活動摘要', 'does_not_support': '無法判定完整分段'}],
        'limitations': ['partial_detail_coverage'],
        'algorithm_version': 'execution-analysis-v1',
        'raw_samples': [{'latitude': 99, 'secret_token': 'never-return'}]}


def _seed(client):
    scope = client.app.dependency_overrides[get_session]()
    session = next(scope)
    ensure_current_user(session, CurrentUser(id='detail-owner'))
    ensure_current_user(session, CurrentUser(id='detail-other'))
    session.add(IntegrationConnectionModel(id='conn-owner', user_id='detail-owner',
        provider='garmin_connect'))
    session.flush()
    session.add(ActivityModel(id='with-detail', user_id='detail-owner',
        provider_connection_id='conn-owner', provider_activity_id='garmin-1',
        started_at=NOW, activity_type='running', duration_seconds=2100,
        distance_meters=4500))
    session.add(ActivityModel(id='without-detail', user_id='detail-owner',
        started_at=NOW, activity_type='running', duration_seconds=1800,
        distance_meters=4000))
    session.add(ActivityModel(id='foreign-detail', user_id='detail-other',
        started_at=NOW, activity_type='running', duration_seconds=1800,
        distance_meters=4000))
    session.flush()
    for identity, fetched, sampling in (
            ('old-snapshot', NOW - timedelta(days=1), 'chart'),
            ('new-snapshot', NOW, 'recorded')):
        session.add(ActivityDetailSnapshotModel(id=identity, user_id='detail-owner',
            activity_id='with-detail', resource='fit', schema_version='test-v1',
            semantic_hash=identity, fetched_at=fetched,
            coverage={'state': 'complete' if sampling == 'recorded' else 'partial',
                      'sampling': sampling, 'covered_seconds': 1800,
                      'missing_channels': [], 'limitations': []},
            source_payload={'secret_token': 'never-return'}))
    session.flush()
    for identity, sampling in (('old-snapshot', 'chart'), ('new-snapshot', 'recorded')):
        session.add(ActivitySegmentModel(user_id='detail-owner', snapshot_id=identity,
            ordinal=0, payload={'source_index': 0, 'source_kind': 'lap',
                'timer_seconds': 1800 if sampling == 'chart' else 2100,
                'distance_meters': 4500, 'metadata': {'secret_token': 'never-return'}}))
    session.add(ActivitySampleChunkModel(user_id='detail-owner', snapshot_id='old-snapshot',
        ordinal=0, sample_count=1, samples=[{'latitude': 99, 'secret_token': 'never-return'}]))
    session.add(ActivityDetailFetchModel(user_id='detail-owner', activity_id='with-detail',
        resource='fit', status='available', current_snapshot_id='new-snapshot'))
    for identity, snapshot, created in (
            ('old-analysis', 'old-snapshot', NOW - timedelta(hours=2)),
            ('new-analysis', 'new-snapshot', NOW - timedelta(hours=1))):
        session.add(ActivityExecutionAnalysisModel(id=identity, user_id='detail-owner',
            activity_id='with-detail', fingerprint=identity,
            algorithm_version='execution-analysis-v1', prescription_revision_id=None,
            snapshot_ids=[snapshot], payload=_analysis('with-detail', snapshot,
                                                       fingerprint=identity), created_at=created))
    session.commit()
    scope.close()


def test_execution_reads_exact_historical_snapshots_without_raw_samples():
    client = create_sqlite_test_client()
    _seed(client)
    latest = client.get('/api/v1/activities/with-detail/execution', headers=HEADERS)
    assert latest.status_code == 200, latest.text
    current = latest.json()['data']
    assert current['analysis_id'] == 'new-analysis'
    assert current['freshness'] == 'current'
    assert current['used_details'][0]['snapshot_id'] == 'new-snapshot'
    assert current['used_details'][0]['segments'][0]['timer_seconds'] == 2100
    historical = client.get('/api/v1/activities/with-detail/execution?analysis_id=old-analysis',
                            headers=HEADERS)
    assert historical.status_code == 200, historical.text
    old = historical.json()['data']
    assert old['analysis_id'] == 'old-analysis'
    assert old['freshness'] == 'stale'
    assert old['used_details'][0]['snapshot_id'] == 'old-snapshot'
    assert old['used_details'][0]['coverage']['sampling'] == 'chart'
    assert old['used_details'][0]['precision'] == 'sampled'
    assert old['used_details'][0]['segments'][0]['timer_seconds'] == 1800
    assert 'secret_token' not in historical.text
    assert 'latitude' not in historical.text
    assert 'raw_samples' not in historical.text


def test_execution_handles_missing_details_and_enforces_activity_and_analysis_ownership():
    client = create_sqlite_test_client()
    _seed(client)
    no_detail = client.get('/api/v1/activities/without-detail/execution', headers=HEADERS)
    assert no_detail.status_code == 200, no_detail.text
    assert no_detail.json()['data']['analysis'] is None
    assert no_detail.json()['data']['freshness'] == 'unavailable'
    assert no_detail.json()['data']['used_details'] == []
    assert client.get('/api/v1/activities/missing/execution', headers=HEADERS).status_code == 404
    assert client.get('/api/v1/activities/foreign-detail/execution', headers=HEADERS).status_code == 404
    assert client.get('/api/v1/activities/with-detail/execution?analysis_id=missing',
                      headers=HEADERS).status_code == 404
    assert client.get('/api/v1/activities/without-detail/execution?analysis_id=old-analysis',
                      headers=HEADERS).status_code == 404
    assert client.get('/api/v1/activities/with-detail/execution',
                      headers={'X-Johnny-User-Id': 'detail-other'}).status_code == 404


def test_detail_coverage_counts_only_owner_and_distinguishes_sampling():
    client = create_sqlite_test_client()
    _seed(client)
    response = client.get('/api/v1/activities/detail-coverage', headers=HEADERS)
    assert response.status_code == 200, response.text
    coverage = response.json()['data']
    assert coverage['total_activities'] == 2
    assert coverage['with_details'] == 1
    assert coverage['without_details'] == 1
    assert coverage['fetch_status_counts'] == {'available': 1}
    assert coverage['sampling_counts'] == {'recorded': 1}
    other = client.get('/api/v1/activities/detail-coverage',
                       headers={'X-Johnny-User-Id': 'detail-other'})
    assert other.status_code == 200
    assert other.json()['data']['total_activities'] == 1
    assert other.json()['data']['with_details'] == 0


def test_latest_analysis_becomes_stale_when_current_snapshot_pointer_changes():
    client = create_sqlite_test_client()
    _seed(client)
    scope = client.app.dependency_overrides[get_session]()
    session = next(scope)
    fetch = session.query(ActivityDetailFetchModel).filter_by(
        user_id='detail-owner', activity_id='with-detail', resource='fit').one()
    fetch.current_snapshot_id = 'old-snapshot'
    session.commit()
    scope.close()
    response = client.get('/api/v1/activities/with-detail/execution', headers=HEADERS)
    assert response.status_code == 200
    result = response.json()['data']
    assert result['analysis_id'] == 'new-analysis'
    assert result['freshness'] == 'stale'
    assert result['used_details'][0]['snapshot_id'] == 'new-snapshot'
    assert result['current_details'][0]['current_snapshot_id'] == 'old-snapshot'


def test_complete_chart_coverage_still_reports_sampled_precision():
    client = create_sqlite_test_client()
    _seed(client)
    scope = client.app.dependency_overrides[get_session]()
    session = next(scope)
    snapshot = session.get(ActivityDetailSnapshotModel, 'old-snapshot')
    snapshot.coverage = {**snapshot.coverage, 'state': 'complete'}
    session.commit()
    scope.close()
    response = client.get('/api/v1/activities/with-detail/execution?analysis_id=old-analysis',
                          headers=HEADERS)
    assert response.status_code == 200
    detail = response.json()['data']['used_details'][0]
    assert detail['coverage']['state'] == 'complete'
    assert detail['coverage']['sampling'] == 'chart'
    assert detail['precision'] == 'sampled'


def test_execution_refuses_analysis_that_names_another_owners_activity():
    client = create_sqlite_test_client()
    _seed(client)
    scope = client.app.dependency_overrides[get_session]()
    session = next(scope)
    analysis = session.get(ActivityExecutionAnalysisModel, 'new-analysis')
    analysis.payload = {**analysis.payload,
                        'activity_ids': ['with-detail', 'foreign-detail']}
    session.commit()
    scope.close()
    response = client.get('/api/v1/activities/with-detail/execution', headers=HEADERS)
    assert response.status_code == 404
