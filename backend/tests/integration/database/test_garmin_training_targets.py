from dataclasses import replace
from datetime import date, datetime, timedelta, timezone

from src.domain.athlete_race import AthleteProfile
from src.domain.training_plan import TrainingPlan, Workout, WorkoutStep, WorkoutTarget
from src.infrastructure.database.models import Base, UserModel
from src.infrastructure.database.integration_repository import SqlAlchemyIntegrationRepository
from src.infrastructure.database.athlete_race_repository import SqlAlchemyAthleteRaceRepository
from src.infrastructure.database.training_plan_repository import SqlAlchemyTrainingPlanRepository


def test_synced_evidence_refreshes_existing_workouts_without_rewriting_history(sqlite_session_factory):
    Base.metadata.create_all(sqlite_session_factory.kw['bind'])
    with sqlite_session_factory() as session:
        user = UserModel(email='targets@example.com', display_name='Runner')
        session.add(user)
        session.flush()
        athletes = SqlAlchemyAthleteRaceRepository(session)
        profile = AthleteProfile.create(user_id=user.id, timezone='UTC', current_weekly_mileage_km=20,
            preferred_training_days=('monday',), preferred_long_run_day='monday', max_runs_per_week=3,
            experience_level='beginner', training_preferences={'threshold_pace_seconds_per_km': 300})
        athletes.save_profile(user.id, profile)
        integrations = SqlAlchemyIntegrationRepository(session)
        conn = integrations.create_connection(user_id=user.id, provider='garmin_connect')
        day = date.today()
        step = WorkoutStep.create(step_type='free_run', duration_seconds=1800, target=WorkoutTarget(kind="rpe", rpe=3, zone="easy"))
        planned = Workout.create(scheduled_for=day, workout_type='easy_run', purpose='Easy', steps=(step,))
        completed = replace(planned, id=None, status='completed')
        plans = SqlAlchemyTrainingPlanRepository(session)
        plan = plans.save_plan(user.id, TrainingPlan.create(user_id=user.id, name='Existing', starts_on=day, ends_on=day,
            workouts=(planned, completed), status='active'))
        integrations.update_training_evidence(user.id, conn.id, 'heart_rate_zones', {'sport':'RUNNING','heart_rate_zones':{'easy':[125,139]}}, checked_at=datetime.now(timezone.utc))
        integrations.update_training_evidence(user.id, conn.id, 'lactate_threshold', {'threshold_pace_seconds_per_km':320,'measured_on':day.isoformat()}, checked_at=datetime.now(timezone.utc))
        loaded = plans.get_plan_for_user(user.id, plan.id)
        target = next(w for w in loaded.workouts if w.status == 'planned').steps[0].target
        assert target.heart_rate_range_bpm == (125,139)
        assert target.pace_range_seconds_per_km == (360,405)
        assert next(w for w in loaded.workouts if w.status == 'completed').steps[0].target.pace_range_seconds_per_km is None
        # Removing the manual override selects Garmin, without regenerating the plan.
        athletes.save_profile(user.id, replace(profile, preferences=replace(profile.preferences, training_preferences={})))
        target = next(w for w in plans.get_current_plan_for_user(user.id).workouts if w.status == 'planned').steps[0].target
        assert target.pace_range_seconds_per_km == (384,432)
        assert target.pace_source == 'garmin_lactate_threshold'
        integrations.update_training_evidence(user.id, conn.id, 'heart_rate_zones', None, checked_at=datetime.now(timezone.utc), failed=True)
        evidence = athletes.get_profile_for_user(user.id).preferences.training_preferences['garmin_training_evidence']
        assert evidence['heart_rate_zones']['status'] == 'stale'
        assert evidence['heart_rate_zones']['heart_rate_zones']['easy'] == [125,139]
        assert integrations.get_training_evidence_for_user('another-user') == {}
        # A replacement beginning tomorrow leaves today's predecessor workout actionable.
        from src.application.training_analytics import resolve_plan_for_date
        tomorrow = day + timedelta(days=1)
        old_future = replace(plan.workouts[0], id=None, scheduled_for=tomorrow)
        plans.save_plan(user.id, replace(plan, status='superseded', ends_on=tomorrow, workouts=(*plan.workouts, old_future)))
        plans.save_plan(user.id, TrainingPlan.create(user_id=user.id, name='Next', starts_on=tomorrow, ends_on=tomorrow,
            workouts=(replace(planned, scheduled_for=tomorrow),), status='active', metadata={'previous_plan_id': plan.id}))
        today_plan = resolve_plan_for_date(plans, user.id, day)
        assert today_plan.status == 'superseded'
        assert next(w for w in today_plan.workouts if w.status == 'planned').steps[0].target.pace_range_seconds_per_km == (384,432)
        predecessor = plans.get_plan_for_user(user.id, plan.id)
        assert next(w for w in predecessor.workouts if w.scheduled_for == tomorrow).steps[0].target == old_future.steps[0].target
        integrations.disconnect_connection(conn.id)
        assert integrations.get_training_evidence_for_user(user.id) == {}


def test_real_sync_keeps_last_good_evidence_on_empty_failed_and_blocked_sync(sqlite_session_factory):
    from src.application.integrations import GarminInitialSyncHandler, GarminInitialSyncCommand, GarminResourceFetchResult, GarminCredentialBlockedError
    from src.infrastructure.database.activity_repository import SqlAlchemyActivityRepository
    from src.infrastructure.database.outbox_repository import SqlAlchemyOutboxRepository
    from src.infrastructure.integrations.garmin_normalizer import normalize_garmin_activity, normalize_garmin_daily_health, normalize_garmin_training_evidence

    class Garmin:
        failure = None
        empty = False

        def fetch_resource(self, *, resource_type, **kwargs):
            if self.failure and resource_type == 'activities':
                raise self.failure
            if self.empty:
                return GarminResourceFetchResult()
            if resource_type == 'heart_rate_zones':
                return GarminResourceFetchResult(items=[{'profiles': [{'sport': 'RUNNING', 'zone1Floor': 100, 'zone2Floor': 120, 'zone3Floor': 140, 'zone4Floor': 160, 'zone5Floor': 180}]}])
            if resource_type == 'lactate_threshold':
                return GarminResourceFetchResult(items=[{'speed_and_heart_rate': {'speed': 3.125, 'calendarDate': '2026-10-10'}}])
            return GarminResourceFetchResult()

    Base.metadata.create_all(sqlite_session_factory.kw['bind'])
    with sqlite_session_factory() as session:
        user = UserModel(email='sync-targets@example.com', display_name='Runner')
        session.add(user)
        session.flush()
        integrations = SqlAlchemyIntegrationRepository(session)
        connection = integrations.create_connection(user_id=user.id, provider='garmin_connect')
        garmin = Garmin()
        handler = GarminInitialSyncHandler(normalize_training_evidence=normalize_garmin_training_evidence, integrations=integrations, activities=SqlAlchemyActivityRepository(session),
            outbox=SqlAlchemyOutboxRepository(session), garmin=garmin, athlete_profiles=SqlAlchemyAthleteRaceRepository(session),
            normalize_activity=normalize_garmin_activity, normalize_health=normalize_garmin_daily_health)
        command = GarminInitialSyncCommand(user_id=user.id, connection_id=connection.id)
        summary = handler.handle(command).to_payload()['resources']
        assert summary['heart_rate_zones']['stored'] == 1
        assert summary['lactate_threshold']['stored'] == 1
        evidence = integrations.get_training_evidence_for_user(user.id)
        assert evidence['heart_rate_zones']['heart_rate_zones']['easy'] == [120, 139]
        assert evidence['lactate_threshold']['threshold_pace_seconds_per_km'] == 320
        synced_at = evidence['lactate_threshold']['synced_at']
        garmin.empty = True
        handler.handle(command)
        evidence = integrations.get_training_evidence_for_user(user.id)
        assert evidence['lactate_threshold']['status'] == 'stale'
        assert evidence['lactate_threshold']['synced_at'] == synced_at
        garmin.empty = False
        handler.handle(command)
        garmin.failure = GarminCredentialBlockedError('reauth required')
        handler.handle(command)
        evidence = integrations.get_training_evidence_for_user(user.id)
        assert evidence['heart_rate_zones']['status'] == 'stale'
        assert evidence['lactate_threshold']['threshold_pace_seconds_per_km'] == 320
        assert evidence['lactate_threshold']['status'] == 'stale'
