from datetime import date, datetime, timedelta, timezone

from src.infrastructure.database.coaching_analysis_evidence_repository import (
    SqlAlchemyCoachingAnalysisEvidenceRepository,
)
from src.infrastructure.database.models import (
    ActivityExecutionAnalysisModel, ActivityModel, Base, UserModel,
)
from src.domain.training_plan import TrainingPlan, Workout
from src.infrastructure.database.training_plan_repository import SqlAlchemyTrainingPlanRepository


def test_execution_analyses_are_owner_and_cutoff_scoped(sqlite_session_factory):
    Base.metadata.create_all(sqlite_session_factory.kw['bind'])
    cutoff = datetime(2027, 1, 15, 23, tzinfo=timezone.utc)
    with sqlite_session_factory() as session:
        for owner in ('athlete', 'other'):
            session.add(UserModel(id=owner, email=f'{owner}@example.test', display_name=owner))
        session.flush()
        for owner in ('athlete', 'other'):
            activity = ActivityModel(id=f'{owner}-activity', user_id=owner,
                started_at=datetime(2027, 1, 15, 16, 30, tzinfo=timezone.utc),
                activity_type='running', duration_seconds=2400, distance_meters=5000)
            session.add(activity)
        session.flush()
        for owner in ('athlete', 'other'):
            session.add(ActivityExecutionAnalysisModel(user_id=owner,
                activity_id=f'{owner}-activity', fingerprint=f'{owner}-hash',
                algorithm_version='execution-analysis-v1', snapshot_ids=[],
                payload={'activity_id': f'{owner}-activity', 'activity_ids': [f'{owner}-activity'],
                         'fingerprint': f'{owner}-hash', 'mapping': 'unmatched',
                         'facts': [], 'findings': [], 'limitations': ['missing_prescription']},
                created_at=cutoff - timedelta(minutes=1)))
        session.flush()
        repo = SqlAlchemyCoachingAnalysisEvidenceRepository(session)
        result = repo.list_execution_analyses('athlete', date(2027, 1, 15),
                                              date(2027, 1, 16), cutoff)
        assert [item.activity_id for item in result] == ['athlete-activity']
        assert result[0].activity_started_at == datetime(2027, 1, 15, 16, 30,
                                                          tzinfo=timezone.utc)
        assert result[0].limitations == ('missing_prescription',)
        assert repo.list_execution_analyses('athlete', date(2027, 1, 15),
                                            date(2027, 1, 16), cutoff - timedelta(minutes=2)) == ()


def test_advice_context_uses_athlete_local_day_and_two_nearest_future_workouts(sqlite_session_factory):
    Base.metadata.create_all(sqlite_session_factory.kw['bind'])
    today = date(2027, 1, 16)
    cutoff = datetime(2027, 1, 15, 23, tzinfo=timezone.utc)
    with sqlite_session_factory() as session:
        session.add(UserModel(id='athlete', email='athlete@example.test', display_name='Athlete'))
        session.flush()
        workouts = tuple(Workout.create(id=f'w-{offset}', scheduled_for=today + timedelta(days=offset),
                                        workout_type='easy_run', purpose='Easy',
                                        planned_duration_minutes=30)
                         for offset in (0, 1, 3, 6, 8))
        SqlAlchemyTrainingPlanRepository(session).save_plan('athlete', TrainingPlan.create(
            id='plan', user_id='athlete', name='Base', starts_on=today,
            ends_on=today + timedelta(days=8), workouts=workouts))
        session.add(ActivityModel(id='activity', user_id='athlete',
            started_at=datetime(2027, 1, 15, 16, 30, tzinfo=timezone.utc),
            activity_type='running', duration_seconds=1800, distance_meters=4000,
            provider_summary={'source': 'manual', 'matched_workout_id': 'w-0'}))
        session.flush()
        repo = SqlAlchemyCoachingAnalysisEvidenceRepository(session)
        context = repo.load_advice_context('athlete', today, 'Asia/Taipei', None, cutoff)
        assert context.workout.id == 'w-0'
        assert [s.workout_id for s in context.today_sessions] == ['w-0']
        assert [w.id for w in context.next_workouts] == ['w-1', 'w-3']
        assert context.activity_sync_usable is False
