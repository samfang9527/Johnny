from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from tests.unit.api_test_helpers import create_sqlite_test_client
from src.api.dependencies import get_session
from src.infrastructure.database.models import AgentTaskModel, DailyAdviceModel
from sqlalchemy import select


def setup():
    client=create_sqlite_test_client()
    headers={'X-Johnny-User-Id':'session-athlete'}
    day=datetime.now(timezone.utc).date().isoformat()
    client.put('/api/v1/athlete/profile',headers=headers,json={'timezone':'UTC','current_weekly_mileage_km':20,'preferred_training_days':['monday'],'preferred_long_run_day':'monday','max_runs_per_week':3})
    plan=client.post('/api/v1/training-plans',headers=headers,json={'name':'p','starts_on':day,'ends_on':day,'workouts':[{'scheduled_for':day,'workout_type':'tempo','purpose':'Tempo','planned_duration_minutes':30}]}).json()['data']
    ids=[]
    for minute in (0,15,30):
        result=client.post('/api/v1/activities',headers=headers,json={'source':'manual','started_at':f'{day}T00:{minute:02d}:00Z','sport_type':'track_running','distance_meters':1000,'duration_seconds':600})
        assert result.status_code==200,result.text
        ids.append(result.json()['data']['id'])
    return client,headers,day,plan['workouts'][0]['id'],ids


def setup_adjacent():
    client = create_sqlite_test_client()
    headers = {'X-Johnny-User-Id': 'adjacent-athlete'}
    today = datetime.now(timezone.utc).date()
    tomorrow = today + timedelta(days=1)
    client.put('/api/v1/athlete/profile', headers=headers, json={
        'timezone': 'UTC', 'current_weekly_mileage_km': 20,
        'preferred_training_days': ['saturday', 'sunday'],
        'preferred_long_run_day': 'sunday', 'max_runs_per_week': 3,
    })
    plan = client.post('/api/v1/training-plans', headers=headers, json={
        'name': 'weekend', 'starts_on': today.isoformat(), 'ends_on': tomorrow.isoformat(),
        'workouts': [
            {'scheduled_for': today.isoformat(), 'workout_type': 'easy_run', 'purpose': 'Saturday easy', 'planned_duration_minutes': 30},
            {'scheduled_for': tomorrow.isoformat(), 'workout_type': 'long_run', 'purpose': 'Sunday long', 'planned_duration_minutes': 60},
        ],
    })
    assert plan.status_code == 200, plan.text
    workouts = {item['scheduled_for']: item['id'] for item in plan.json()['data']['workouts']}
    activity = client.post('/api/v1/activities', headers=headers, json={
        'source': 'manual', 'started_at': f'{today.isoformat()}T10:00:00Z',
        'sport_type': 'running', 'distance_meters': 10000, 'duration_seconds': 3600,
    })
    assert activity.status_code == 200, activity.text
    return client, headers, today, workouts, activity.json()['data']['id']


def test_adjacent_workout_can_be_manually_paired_without_changing_activity_date():
    client, headers, today, workouts, activity_id = setup_adjacent()
    url = '/api/v1/activities/session-reviews'
    card = client.get(url, headers=headers, params={'anchor_date': today.isoformat()}).json()['data'][0]
    assert card['status'] == 'automatic'
    assert {item['scheduled_for'] for item in card['candidates']} == {today.isoformat(), (today + timedelta(days=1)).isoformat()}
    response = client.post(url, headers=headers, json={
        'activity_ids': [activity_id],
        'groups': [{'activity_ids': [activity_id], 'workout_id': workouts[(today + timedelta(days=1)).isoformat()]}],
    })
    assert response.status_code == 200, response.text
    saved = client.get(url, headers=headers, params={'anchor_date': today.isoformat()}).json()['data'][0]
    assert saved['local_date'] == today.isoformat()
    assert saved['workout_id'] == workouts[(today + timedelta(days=1)).isoformat()]
    assert saved['status'] == 'confirmed'


def test_one_workout_cannot_be_claimed_by_two_sessions():
    client, headers, today, workouts, first_id = setup_adjacent()
    second = client.post('/api/v1/activities', headers=headers, json={
        'source': 'manual', 'started_at': f'{today.isoformat()}T15:00:00Z',
        'sport_type': 'running', 'distance_meters': 5000, 'duration_seconds': 1800,
    })
    assert second.status_code == 200, second.text
    second_id = second.json()['data']['id']
    url = '/api/v1/activities/session-reviews'
    target = workouts[(today + timedelta(days=1)).isoformat()]
    duplicate = client.post(url, headers=headers, json={
        'activity_ids': [first_id, second_id],
        'groups': [
            {'activity_ids': [first_id], 'workout_id': target},
            {'activity_ids': [second_id], 'workout_id': target},
        ],
    })
    assert duplicate.status_code == 409
    first = client.post(url, headers=headers, json={
        'activity_ids': [first_id], 'groups': [{'activity_ids': [first_id], 'workout_id': target}],
    })
    assert first.status_code == 200, first.text
    cards = client.get(url, headers=headers, params={'anchor_date': today.isoformat()}).json()['data']
    second_card = next(card for card in cards if second_id in {item['id'] for item in card['activities']})
    assert target not in {candidate['id'] for candidate in second_card['candidates']}
    claimed = client.post(url, headers=headers, json={
        'activity_ids': [second_id], 'groups': [{'activity_ids': [second_id], 'workout_id': target}],
    })
    assert claimed.status_code == 409


def test_adjacent_claimed_sessions_can_exchange_workouts_atomically():
    client = create_sqlite_test_client()
    headers = {'X-Johnny-User-Id': 'swap-athlete'}
    sunday = datetime.now(ZoneInfo('Asia/Taipei')).date()
    saturday = sunday - timedelta(days=1)
    client.put('/api/v1/athlete/profile', headers=headers, json={
        'timezone': 'Asia/Taipei', 'current_weekly_mileage_km': 20,
        'preferred_training_days': ['saturday', 'sunday'],
        'preferred_long_run_day': 'sunday', 'max_runs_per_week': 3,
    })
    response = client.post('/api/v1/training-plans', headers=headers, json={
        'name': 'weekend', 'starts_on': saturday.isoformat(), 'ends_on': sunday.isoformat(),
        'workouts': [
            {'scheduled_for': saturday.isoformat(), 'workout_type': 'easy_run', 'purpose': 'Easy', 'planned_duration_minutes': 30},
            {'scheduled_for': sunday.isoformat(), 'workout_type': 'long_run', 'purpose': 'Long', 'planned_duration_minutes': 60},
        ],
    })
    assert response.status_code == 200, response.text
    workouts = {item['scheduled_for']: item['id'] for item in response.json()['data']['workouts']}
    ids = []
    for day, minute in ((saturday, 0), (saturday, 20), (sunday, 0)):
        activity = client.post('/api/v1/activities', headers=headers, json={
            'source': 'manual', 'started_at': f'{day.isoformat()}T08:{minute:02d}:00Z',
            'sport_type': 'running', 'distance_meters': 4000, 'duration_seconds': 900,
        })
        assert activity.status_code == 200, activity.text
        ids.append(activity.json()['data']['id'])
    url = '/api/v1/activities/session-reviews'
    for group_ids, workout_id in ((ids[:2], workouts[saturday.isoformat()]), ([ids[2]], workouts[sunday.isoformat()])):
        response = client.post(url, headers=headers, json={
            'activity_ids': group_ids, 'groups': [{'activity_ids': group_ids, 'workout_id': workout_id}],
        })
        assert response.status_code == 200, response.text
    cards = client.get(url, headers=headers, params={'anchor_date': sunday.isoformat()}).json()['data']
    saturday_card = next(card for card in cards if card['local_date'] == saturday.isoformat())
    assert [candidate['id'] for candidate in saturday_card['swap_candidates']] == [workouts[sunday.isoformat()]]
    swapped = client.post(f'{url}/swap', headers=headers, json={
        'activity_ids': ids[:2], 'workout_id': workouts[sunday.isoformat()],
    })
    assert swapped.status_code == 200, swapped.text
    cards = client.get(url, headers=headers, params={'anchor_date': sunday.isoformat()}).json()['data']
    by_day = {card['local_date']: card for card in cards}
    assert by_day[saturday.isoformat()]['workout_id'] == workouts[sunday.isoformat()]
    assert by_day[sunday.isoformat()]['workout_id'] == workouts[saturday.isoformat()]
    assert {item['id'] for item in by_day[saturday.isoformat()]['activities']} == set(ids[:2])
    assert by_day[sunday.isoformat()]['activities'][0]['id'] == ids[2]
    assert by_day[saturday.isoformat()]['swap_candidates'][0]['activity_date'] == sunday.isoformat()
    undone = client.post(f'{url}/swap', headers=headers, json={
        'activity_ids': ids[:2], 'workout_id': workouts[saturday.isoformat()],
    })
    assert undone.status_code == 200, undone.text
    cards = client.get(url, headers=headers, params={'anchor_date': sunday.isoformat()}).json()['data']
    by_day = {card['local_date']: card for card in cards}
    assert by_day[saturday.isoformat()]['workout_id'] == workouts[saturday.isoformat()]
    assert by_day[sunday.isoformat()]['workout_id'] == workouts[sunday.isoformat()]


def test_review_confirm_split_unplanned_persist_without_automatic_advice():
    client,h,day,w,ids=setup()
    url='/api/v1/activities/session-reviews'
    response=client.get(url,headers=h,params={'anchor_date':day})
    assert response.status_code==200,response.text
    card=response.json()['data'][0]
    assert card['status']=='automatic' and card['workout_id']==w
    assert card['duration_seconds']==1800
    decision={'activity_ids':ids,'groups':[{'activity_ids':ids,'workout_id':w}]}
    assert client.post(url,headers=h,json=decision).status_code==200
    assert client.get(url,headers=h,params={'anchor_date':day}).json()['data'][0]['status']=='confirmed'
    partition={'activity_ids':ids,'groups':[{'activity_ids':ids[:2],'workout_id':w},{'activity_ids':ids[2:],'workout_id':None}]}
    assert client.post(url,headers=h,json=partition).status_code==200
    cards=client.get(url,headers=h,params={'anchor_date':day}).json()['data']
    assert [x['status'] for x in cards]==['confirmed','unplanned']
    sessions=client.app.dependency_overrides[get_session]()
    s=next(sessions)
    assert s.scalar(select(AgentTaskModel).where(AgentTaskModel.task_type=='agent.workflow')) is None
    assert s.scalar(select(DailyAdviceModel)) is None
    sessions.close()


def test_decisions_reject_foreign_ids_incomplete_partition_and_partial_saved_group():
    client,h,day,w,ids=setup()
    url='/api/v1/activities/session-reviews'
    decision={'activity_ids':ids,'groups':[{'activity_ids':ids,'workout_id':w}]}
    assert client.post(url,headers={'X-Johnny-User-Id':'other'},json=decision).status_code==404
    assert client.post(url,headers=h,json={'activity_ids':ids,'groups':[{'activity_ids':ids[:1],'workout_id':w}]}).status_code==400
    assert client.post(url,headers=h,json={'activity_ids':ids,'groups':[{'activity_ids':ids,'workout_id':'foreign'}]}).status_code==404
    assert client.post(url,headers=h,json=decision).status_code==200
    assert client.post(url,headers=h,json={'activity_ids':ids[:1],'groups':[{'activity_ids':ids[:1],'workout_id':None}]}).status_code==409


def test_saved_partition_survives_reimport_and_is_used_by_fresh_advice_facts():
    from src.application.daily_advice_context import load_week_execution
    from src.infrastructure.database.activity_repository import SqlAlchemyActivityRepository
    from src.infrastructure.database.training_plan_repository import SqlAlchemyTrainingPlanRepository
    from src.domain.activity_health import CompletedActivity
    from dataclasses import replace
    client,h,day,w,ids=setup()
    url='/api/v1/activities/session-reviews'
    assert client.post(url,headers=h,json={'activity_ids':ids,'groups':[{'activity_ids':ids[:2],'workout_id':w},{'activity_ids':ids[2:],'workout_id':None}]}).status_code==200
    scope=client.app.dependency_overrides[get_session]()
    s=next(scope)
    repo=SqlAlchemyActivityRepository(s)
    a=repo.get_activity_for_user('session-athlete',ids[0])
    # Refreshing provider fields must not erase the athlete's saved decision.
    repo.save_activity('session-athlete',replace(a,match_reviewed=False,session_group_id=None,matched_workout_id=None))
    loaded=repo.get_activity_for_user('session-athlete',ids[0])
    assert loaded.match_reviewed and loaded.matched_workout_id==w
    plan=SqlAlchemyTrainingPlanRepository(s).get_current_plan_for_user('session-athlete')
    facts=load_week_execution(training_data=repo,plan=plan,user_id='session-athlete',anchor_date=date.fromisoformat(day),as_of=datetime.now(timezone.utc)+timedelta(days=1),timezone_name='UTC',activity_coverage_complete=True)
    assert (facts.completed_count,facts.extra_count,facts.actual_minutes)==(1,1,30)
    scope.close()


def test_repeated_review_does_not_queue_manual_advice_after_complete_sync():
    from src.infrastructure.database.models import SyncRunModel, IntegrationConnectionModel
    client,h,day,w,ids=setup()
    url='/api/v1/activities/session-reviews'
    decision={'activity_ids':ids,'groups':[{'activity_ids':ids,'workout_id':w}]}
    client.post(url,headers=h,json=decision)
    scope=client.app.dependency_overrides[get_session]()
    s=next(scope)
    connection=IntegrationConnectionModel(user_id='session-athlete',provider='garmin_connect')
    s.add(connection); s.flush()
    sync=SyncRunModel(integration_connection_id=connection.id,status='succeeded',finished_at=datetime.now(timezone.utc),summary={'resources':{'activities':{'failed':0},'sleep':{'failed':0}}})
    s.add(sync); s.flush()
    s.commit(); scope.close()
    response=client.post(url,headers=h,json=decision)
    assert response.status_code == 200, response.text
    assert response.json()['data']['refresh_runs'] == []
    scope=client.app.dependency_overrides[get_session]()
    s=next(scope)
    assert s.scalar(select(AgentTaskModel).where(AgentTaskModel.task_type=='agent.workflow')) is None
    scope.close()


def test_review_window_includes_seventh_local_date_and_rejects_older_changes():
    client, headers, today, _, _ = setup()
    today_date = date.fromisoformat(today)
    seventh_day = (today_date - timedelta(days=6)).isoformat()
    expired_day = (today_date - timedelta(days=7)).isoformat()
    ids = {}
    for day in (seventh_day, expired_day):
        response = client.post('/api/v1/activities', headers=headers, json={
            'source': 'manual', 'started_at': f'{day}T12:00:00Z',
            'sport_type': 'running', 'distance_meters': 1000, 'duration_seconds': 600,
        })
        assert response.status_code == 200, response.text
        ids[day] = response.json()['data']['id']

    url = '/api/v1/activities/session-reviews'
    visible = client.get(url, headers=headers, params={'anchor_date': today}).json()['data']
    assert seventh_day in {item['local_date'] for item in visible}
    assert expired_day not in {item['local_date'] for item in visible}
    assert client.get(url, headers=headers, params={'anchor_date': expired_day}).json()['data'] == []

    def unplanned_decision(day):
        return {'activity_ids': [ids[day]], 'groups': [{'activity_ids': [ids[day]], 'workout_id': None}]}

    assert client.post(url, headers=headers, json=unplanned_decision(seventh_day)).status_code == 200
    expired = client.post(url, headers=headers, json=unplanned_decision(expired_day))
    assert expired.status_code == 409
