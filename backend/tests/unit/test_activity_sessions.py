from dataclasses import replace
from datetime import date, datetime, timedelta, timezone

import pytest

from src.domain.activity_health import CompletedActivity
from src.domain.activity_sessions import match_sessions
from src.domain.daily_advice import build_week_execution
from src.domain.training_plan import TrainingPlan, Workout

DAY = date(2026, 10, 13)

def run(id, minute, duration=10, sport='running', **kwargs):
    return CompletedActivity.create(id=id, user_id='u', source='manual',
        started_at=datetime(2026, 10, 13, 10, tzinfo=timezone.utc) + timedelta(minutes=minute),
        duration_seconds=duration*60, distance_meters=1000, sport_type=sport, **kwargs)

def workout(id='w'):
    return Workout.create(id=id, scheduled_for=DAY, workout_type='tempo', purpose='Tempo', planned_duration_minutes=37)

def test_track_trail_and_running_form_one_session_with_active_time_only():
    recordings=(run('a',0,sport='track_running'),run('b',15,sport='trail_running'),run('c',30))
    sessions=match_sessions(recordings,(workout(),),'Asia/Taipei')
    assert len(sessions)==1
    assert sessions[0].workout_id=='w'
    assert sessions[0].status=='automatic'
    assert sessions[0].duration_seconds==1800
    p=TrainingPlan.create(user_id='u',name='p',starts_on=DAY,ends_on=DAY+timedelta(days=6),workouts=(workout(),))
    facts=build_week_execution(p,recordings,anchor_date=DAY+timedelta(days=1),as_of=datetime(2026,10,14,tzinfo=timezone.utc),timezone_name='Asia/Taipei',activity_coverage_complete=True)
    assert (facts.completed_count,facts.missed_count,facts.extra_count,facts.actual_minutes)==(1,0,0,30)

@pytest.mark.parametrize('start,count',[(40,1),(40.01,2),(9,2)])
def test_end_to_start_gap_and_overlap(start,count):
    assert len(match_sessions((run('a',0),run('b',start)),(), 'UTC'))==count

def test_midnight_and_two_distinct_sessions_stay_separate():
    a=replace(run('a',0),started_at=datetime(2026,10,13,15,45,tzinfo=timezone.utc))
    b=replace(run('b',0),started_at=datetime(2026,10,13,16,5,tzinfo=timezone.utc))
    assert len(match_sessions((a,b),(),'Asia/Taipei'))==2
    sessions=match_sessions((run('a',0),run('b',180)),(workout(),),'UTC')
    assert all(s.status=='needs_review' and s.workout_id is None for s in sessions)

def test_multiple_workouts_need_review_and_explicit_decisions_win():
    assert match_sessions((run('a',0),),(workout('w'),workout('v')),'UTC')[0].status=='needs_review'
    a=run('a',0,session_group_id='saved',match_reviewed=True,matched_workout_id='w')
    b=run('b',15,session_group_id='extra',match_reviewed=True)
    sessions=match_sessions((a,b,run('new',30)),(workout(),),'UTC')
    assert len(sessions)==3
    assert [s.status for s in sessions]==['confirmed','unplanned','unplanned']
    assert sessions[0].workout_id=='w'


def test_explicit_extra_stays_counted_when_other_sessions_need_review():
    recordings=(run('extra',0,match_reviewed=True,session_group_id='extra'),run('a',180),run('b',360))
    p=TrainingPlan.create(user_id='u',name='p',starts_on=DAY,ends_on=DAY+timedelta(days=6),workouts=(workout(),))
    facts=build_week_execution(p,recordings,anchor_date=DAY+timedelta(days=1),as_of=datetime(2026,10,14,tzinfo=timezone.utc),timezone_name='UTC',activity_coverage_complete=True)
    assert facts.extra_count==1
    assert facts.missed_count==0
    assert facts.actual_minutes==30


def test_running_family_counts_in_load_but_trail_cannot_anchor_road_pace():
    from src.domain.training_analytics import TrainingLoadService
    from src.application.training_targets import build_target_profile_from_payloads
    recordings=(run('a',0,sport='track_running'),run('b',15,sport='trail_running'),run('c',30,sport='cycling'))
    load=TrainingLoadService().calculate(user_id='u',anchor_date=DAY,activities=recordings)
    assert load.weekly_distance_meters==2000
    assert load.acute_load==20
    prior={'workouts':[{'id':'race','workout_type':'race','status':'completed','planned_distance_meters':10000}]}
    base={'id':'race-result','started_at':'2026-10-13T10:00:00Z','matched_workout_id':'race','distance_meters':10000,'duration_seconds':3000}
    def profile(sport):
        return build_target_profile_from_payloads({},None,({**base,'sport_type':sport},),prior)
    assert profile('track_running').pace_source=='completed_race'
    assert profile('trail_running').pace_zones=={}


def test_actual_three_recording_regression():
    recordings=tuple(replace(run(str(i),0,sport='track_running'),started_at=datetime.fromisoformat(stamp),duration_seconds=duration)
        for i,(stamp,duration) in enumerate([('2026-10-13T10:35:12+00:00',928),('2026-10-13T10:53:56+00:00',1225),('2026-10-13T11:15:57+00:00',924)]))
    session=match_sessions(recordings,(workout(),),'Asia/Taipei')[0]
    assert len(session.activities)==3 and session.duration_seconds==3077 and session.workout_id=='w'
