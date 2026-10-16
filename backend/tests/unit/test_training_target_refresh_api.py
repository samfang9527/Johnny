from datetime import datetime, timezone

import pytest

from tests.unit.api_test_helpers import create_sqlite_test_client
from src.api.dependencies import get_session
from src.infrastructure.database.integration_repository import SqlAlchemyIntegrationRepository


@pytest.mark.parametrize("athlete_timezone", ["UTC"])
def test_settings_and_garmin_refresh_today_and_plan_without_regeneration(athlete_timezone):
    client = create_sqlite_test_client()
    headers = {'X-Johnny-User-Id': 'target-runner'}
    day = datetime.now(timezone.utc).date().isoformat()
    profile = {'timezone': athlete_timezone, 'current_weekly_mileage_km': 20, 'preferred_training_days': ['monday'],
               'preferred_long_run_day': 'monday', 'max_runs_per_week': 3}
    assert client.put('/api/v1/athlete/profile', headers=headers, json=profile).status_code == 200
    workout = {'scheduled_for': day, 'workout_type': 'easy_run', 'purpose': 'Easy', 'planned_duration_minutes': 30,
               'steps': [{'type': 'free_run', 'duration_seconds': 1800, 'target': {'kind': 'rpe', 'rpe': 3, 'zone': 'easy'}}]}
    created = client.post('/api/v1/training-plans', headers=headers, json={'name': 'Existing', 'starts_on': day, 'ends_on': day,
                         'workouts': [workout, {**workout, 'status': 'completed'}]})
    assert created.status_code == 200
    plan_id = created.json()['data']['id']
    assert client.put('/api/v1/athlete/profile', headers=headers, json={**profile, 'threshold_pace_seconds_per_km': 300}).status_code == 200

    def targets(path, key):
        response = client.get(path, headers=headers)
        assert response.status_code == 200, response.text
        return {w['status']: w['steps'][0]['target'] for w in response.json()['data'][key]}

    current = targets('/api/v1/today?anchor_date=' + day, 'scheduled_workouts')
    assert current['planned']['pace_range_seconds_per_km'] == [360, 405]
    assert current['completed']['pace_range_seconds_per_km'] is None
    assert targets('/api/v1/training-plans/' + plan_id, 'workouts')['planned'] == current['planned']
    # Sync stores evidence independently of athlete settings and never overrides the manual pace.
    sessions = client.app.dependency_overrides[get_session]()
    session = next(sessions)
    integrations = SqlAlchemyIntegrationRepository(session)
    connection = integrations.create_connection(user_id='target-runner', provider='garmin_connect')
    integrations.update_training_evidence('target-runner', connection.id, 'heart_rate_zones',
        {'sport': 'RUNNING', 'heart_rate_zones': {'easy': [120, 139]}}, checked_at=datetime.now(timezone.utc))
    integrations.update_training_evidence('target-runner', connection.id, 'lactate_threshold',
        {'threshold_pace_seconds_per_km': 320}, checked_at=datetime.now(timezone.utc))
    session.commit()
    sessions.close()
    current = targets('/api/v1/today?anchor_date=' + day, 'scheduled_workouts')
    assert current['planned']['heart_rate_range_bpm'] == [120, 139]
    assert current['planned']['pace_range_seconds_per_km'] == [360, 405]
    assert current['planned']['rpe'] == 3
    saved = client.put('/api/v1/athlete/profile', headers=headers, json={**profile, 'threshold_pace_seconds_per_km': None})
    assert saved.json()['data']['garmin_training_evidence']['lactate_threshold']['threshold_pace_seconds_per_km'] == 320
    current = targets('/api/v1/training-plans/' + plan_id, 'workouts')
    assert current['planned']['pace_range_seconds_per_km'] == [384, 432]
    assert current['planned']['pace_source'] == 'garmin_lactate_threshold'
    assert current['completed']['pace_range_seconds_per_km'] is None
    assert client.get('/api/v1/training-plans/' + plan_id, headers={'X-Johnny-User-Id': 'other'}).status_code == 404
