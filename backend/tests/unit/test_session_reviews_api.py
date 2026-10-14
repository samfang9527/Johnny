from datetime import date, datetime, timedelta, timezone

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


def test_review_confirm_split_unplanned_persist_and_queue_advice():
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
    assert s.scalar(select(AgentTaskModel).where(AgentTaskModel.task_type=='agent.workflow')) is not None
    assert s.scalar(select(DailyAdviceModel)).state=='pending'
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


def test_repeated_review_does_not_turn_complete_sync_into_limited_recovery():
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
    advice=s.scalar(select(DailyAdviceModel))
    advice.source_sync_run_id=sync.id
    advice.data_freshness='stale'
    s.commit(); scope.close()
    response=client.post(url,headers=h,json=decision)
    run=response.json()['data']['refresh_runs'][0]['run_id']
    scope=client.app.dependency_overrides[get_session]()
    s=next(scope)
    tasks=s.scalars(select(AgentTaskModel)).all()
    task=next(t for t in tasks if t.payload.get('run_id')==run)
    assert task.payload['input']['limited_recovery'] is False
    scope.close()
