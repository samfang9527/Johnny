"""The two coaching workflows publish bounded analysis without applying proposals."""

import json
from datetime import date, datetime, timezone

import pytest

from src.application.coaching_analysis_generation import generate_coaching_analysis
from src.application.coaching_approval import CoachingApprovalService, CoachingDecisionConflict
from src.application.training_review_generation import GenerateTrainingReviewHandler
from src.application.workout_advice_generation import GenerateWorkoutAdviceHandler
from src.domain.activity_details import DetailCoverage, NormalizedDetails
from src.domain.activity_health import DailyHealthMetrics
from src.domain.athlete_race import AthleteProfile
from src.domain.agent_runtime import ModelResponse, TokenUsage
from src.domain.training_plan import TrainingPlan, Workout, WorkoutStep, WorkoutTarget
from src.domain.workout_advice import WorkoutAdviceConstraints
from src.infrastructure.database.activity_repository import SqlAlchemyActivityRepository
from src.infrastructure.database.activity_detail_repository import SqlAlchemyActivityDetailRepository
from src.infrastructure.database.athlete_race_repository import SqlAlchemyAthleteRaceRepository
from src.infrastructure.database.coaching_repository import SqlAlchemyCoachingRepository
from src.infrastructure.database.models import (
    ActivityExecutionAnalysisModel, ActivityModel, Base, IntegrationConnectionModel, SyncRunModel, UserModel,
)
from src.infrastructure.database.training_plan_repository import SqlAlchemyTrainingPlanRepository


TODAY = date(2027, 1, 16)
NOW = datetime(2027, 1, 15, 23, tzinfo=timezone.utc)


class FakeGateway:
    def __init__(self, *, fail=False):
        self.requests = []
        self.fail = fail

    def complete(self, request):
        self.requests.append(request)
        if self.fail:
            raise TimeoutError('provider unavailable')
        ref = 'workout:today' if request.workflow_name == 'workout_advice' else 'evidence:window'
        return ModelResponse(content=json.dumps({
            'headline': '先留意今天的身體狀況',
            'summary': '依已知資料保守執行，異常時先停止。',
            'findings': [{'observation': '可用資料有限。',
                          'interpretation': '應配合體感判斷。', 'evidence_refs': [ref]}],
            'actions': [{'action_id': 'inspect_evidence', 'text': '先檢視資料。',
                         'evidence_refs': [ref]}],
            'limitations': [], 'evidence_refs': [ref],
        }, ensure_ascii=False), provider='openai', model='fake-model',
            token_usage=TokenUsage(input_tokens=11, output_tokens=13))


@pytest.mark.parametrize('decision', ['accept', 'invalidate', 'invalidate_detail', 'reject'])
def test_advice_uses_gateway_without_raw_recovery_dump_or_early_plan_change(
        sqlite_session_factory, decision):
    Base.metadata.create_all(sqlite_session_factory.kw['bind'])
    with sqlite_session_factory() as session:
        session.add(UserModel(id='athlete', email='athlete@example.test', display_name='Runner'))
        session.flush()
        plans = SqlAlchemyTrainingPlanRepository(session)
        workout = Workout.create(id='run', scheduled_for=TODAY, workout_type='easy_run',
            purpose='Easy', planned_duration_minutes=40,
            steps=(WorkoutStep.create(step_type='free_run', duration_seconds=2400,
                                      target=WorkoutTarget.rpe(3)),))
        plans.save_plan('athlete', TrainingPlan.create(user_id='athlete', name='Base',
            starts_on=TODAY, ends_on=TODAY, workouts=(workout,)))
        session.add(IntegrationConnectionModel(id='prior-connection', user_id='athlete',
                                               provider='garmin_connect'))
        session.flush()
        session.add(ActivityModel(id='prior-run', user_id='athlete',
            provider_connection_id='prior-connection', provider_activity_id='provider-prior-run',
            started_at=datetime(2027, 1, 14, 16, 30, tzinfo=timezone.utc),
            activity_type='running', duration_seconds=2100, distance_meters=5000))
        session.flush()
        historical_analysis = ActivityExecutionAnalysisModel(user_id='athlete',
            activity_id='prior-run', fingerprint='prior-fingerprint',
            algorithm_version='execution-analysis-v1', snapshot_ids=[],
            payload={'activity_id': 'prior-run', 'activity_ids': ['prior-run'],
                     'fingerprint': 'prior-fingerprint', 'mapping': 'unmatched',
                     'facts': [], 'findings': [], 'limitations': ['missing_prescription']},
            created_at=NOW)
        session.add(historical_analysis)
        session.flush()
        activities = SqlAlchemyActivityRepository(session)
        activities.save_daily_health_metrics('athlete', DailyHealthMetrics.create(
            user_id='athlete', metric_date=TODAY, sleep_duration_minutes=300,
            hrv_ms=35, hrv_baseline_ms=50, stress_score=75, body_battery_score=20))
        gateway = FakeGateway()
        handler = GenerateWorkoutAdviceHandler(coaching=SqlAlchemyCoachingRepository(session),
            plans=plans, activities=activities, now=lambda: NOW,
            gateway=gateway, analysis_generator=generate_coaching_analysis)
        result = handler.handle(user_id='athlete', advice_date=TODAY,
            timezone_name='Asia/Taipei', workout_id='run',
            constraints=WorkoutAdviceConstraints(), run_id='advice-run', activity_sync_usable=True)
        assert len(gateway.requests) == 1
        assert result['analysis']['analysis_mode'] == 'llm'
        assert result['analysis']['input_fingerprint'] == result['evidence_fingerprint']
        assert result['evidence_manifest']['recent_analyses'][0]['analysis_id'] == historical_analysis.id
        assert '300' not in result['guidance']
        assert result['recovery']['days'][-1]['signals']['sleep']['value'] == 300
        assert result['recommendation_id']
        assert plans.get_plan_for_date_raw('athlete', TODAY).workouts[0].status == 'planned'
        review = GenerateTrainingReviewHandler(coaching=SqlAlchemyCoachingRepository(session),
            evidence=SqlAlchemyCoachingRepository(session), gateway=gateway,
            analysis_generator=generate_coaching_analysis, now=lambda: NOW).handle(
                user_id='athlete', publication_date=TODAY, timezone_name='Asia/Taipei',
                run_id='review-run')
        assert review['analysis']['input_fingerprint'] != result['analysis']['input_fingerprint']
        assert SqlAlchemyCoachingRepository(session).get_advice_slot('athlete', TODAY, 'run')['freshness'] == 'current'
        assert SqlAlchemyCoachingRepository(session).get_review_slot('athlete', TODAY)['freshness'] == 'current'
        if decision == 'invalidate_detail':
            SqlAlchemyActivityDetailRepository(session).save_snapshot(
                user_id='athlete', fetched_at=NOW,
                details=NormalizedDetails(activity_id='prior-run', resource='fit',
                    schema_version='acceptance-v1',
                    coverage=DetailCoverage(state='complete', sampling='recorded')))
            with pytest.raises(CoachingDecisionConflict, match='evidence_manifest_changed'):
                CoachingApprovalService(session, now=lambda: NOW).accept(
                    'athlete', result['recommendation_id'])
            assert plans.get_plan_for_date_raw('athlete', TODAY).workouts[0].status == 'planned'
        elif decision == 'invalidate':
            SqlAlchemyAthleteRaceRepository(session).save_profile('athlete', AthleteProfile.create(
                user_id='athlete', timezone='Asia/Taipei', experience_level='intermediate',
                current_weekly_mileage_km=35, preferred_training_days=('sunday',),
                preferred_long_run_day='sunday', max_runs_per_week=4))
            with pytest.raises(CoachingDecisionConflict, match='evidence_manifest_changed'):
                CoachingApprovalService(session, now=lambda: NOW).accept(
                    'athlete', result['recommendation_id'])
            assert plans.get_plan_for_date_raw('athlete', TODAY).workouts[0].status == 'planned'
        elif decision == 'reject':
            CoachingApprovalService(session, now=lambda: NOW).reject(
                'athlete', result['recommendation_id'])
            repeated = handler.handle(user_id='athlete', advice_date=TODAY,
                timezone_name='Asia/Taipei', workout_id='run',
                constraints=WorkoutAdviceConstraints(), run_id='advice-repeat',
                activity_sync_usable=True)
            assert repeated['mode'] == 'previously_declined'
            assert repeated.get('recommendation_id') is None
            assert '調整建議' not in repeated['analysis']['headline']
        else:
            CoachingApprovalService(session, now=lambda: NOW).accept(
                'athlete', result['recommendation_id'])
            assert plans.get_plan_for_date_raw('athlete', TODAY).workouts[0].status == 'skipped'


def test_review_calls_gateway_even_without_completed_comparison_and_falls_back(sqlite_session_factory):
    Base.metadata.create_all(sqlite_session_factory.kw['bind'])
    with sqlite_session_factory() as session:
        session.add(UserModel(id='reviewer', email='reviewer@example.test', display_name='Runner'))
        session.flush()
        coaching = SqlAlchemyCoachingRepository(session)
        gateway = FakeGateway()
        handler = GenerateTrainingReviewHandler(coaching=coaching, evidence=coaching,
            gateway=gateway, analysis_generator=generate_coaching_analysis,
            now=lambda: NOW)
        result = handler.handle(user_id='reviewer', publication_date=TODAY,
            timezone_name='Asia/Taipei', run_id='review-run')
        assert len(gateway.requests) == 1
        assert gateway.requests[0].prompt_version == 'johnny-review-analysis-v2'
        assert result['analysis']['analysis_mode'] == 'llm'
        assert '分數' not in result['narrative']
        failed = FakeGateway(fail=True)
        fallback = GenerateTrainingReviewHandler(coaching=coaching, evidence=coaching,
            gateway=failed, analysis_generator=generate_coaching_analysis,
            now=lambda: NOW).handle(user_id='reviewer', publication_date=TODAY,
                                     timezone_name='Asia/Taipei', run_id='review-retry')
        assert len(failed.requests) == 2
        assert fallback['analysis']['analysis_mode'] == 'rules'
        assert fallback['analysis']['fallback_reason'] == 'timeout'
        assert fallback['narrative']


@pytest.mark.parametrize('case', ['unplanned_activity', 'missed', 'uncertain', 'completed_no_detail'])
def test_review_analyzes_non_completed_states(sqlite_session_factory, case):
    Base.metadata.create_all(sqlite_session_factory.kw['bind'])
    with sqlite_session_factory() as session:
        user_id = f'review-{case}'
        session.add(UserModel(id=user_id, email=f'{case}@example.test', display_name='Runner'))
        session.flush()
        coaching = SqlAlchemyCoachingRepository(session)
        if case == 'unplanned_activity':
            session.add(ActivityModel(id=f'activity-{case}', user_id=user_id,
                started_at=datetime(2027, 1, 15, 10, tzinfo=timezone.utc),
                activity_type='running', duration_seconds=1800, distance_meters=4000))
            session.flush()
        else:
            workout = Workout.create(id=f'workout-{case}', scheduled_for=date(2027, 1, 15),
                workout_type='easy_run', purpose='Easy', planned_duration_minutes=35)
            plan = SqlAlchemyTrainingPlanRepository(session).save_plan(user_id,
                TrainingPlan.create(user_id=user_id, name='Base',
                    starts_on=date(2027, 1, 15), ends_on=TODAY, workouts=(workout,)))
            if case == 'completed_no_detail':
                session.add(ActivityModel(id=f'activity-{case}', user_id=user_id,
                    started_at=datetime(2027, 1, 15, 10, tzinfo=timezone.utc),
                    activity_type='running', duration_seconds=2100, distance_meters=4500,
                    provider_summary={'matched_workout_id': workout.id}))
                session.flush()
            if case == 'uncertain':
                coaching.record_prescription_revision(user_id=user_id, plan_id=plan.id,
                    workout=workout, effective_at=datetime(2027, 1, 15, 12,
                    tzinfo=timezone.utc), source='legacy_backfill',
                    confidence='legacy_uncertain', recommendation_id=None)
            else:
                session.add(IntegrationConnectionModel(id=f'connection-{case}',
                    user_id=user_id, provider='garmin_connect'))
                session.add(SyncRunModel(integration_connection_id=f'connection-{case}',
                    status='completed', finished_at=NOW,
                    summary={'activity_coverage': {
                        'starts_on': '2027-01-15', 'ends_on': '2027-01-15',
                        'timezone_name': 'Asia/Taipei', 'pagination_complete': True},
                        'resources': {'activities': {'failed': 0}}}))
                session.flush()
        gateway = FakeGateway()
        result = GenerateTrainingReviewHandler(coaching=coaching, evidence=coaching,
            gateway=gateway, analysis_generator=generate_coaching_analysis,
            now=lambda: NOW).handle(user_id=user_id, publication_date=TODAY,
                                     timezone_name='Asia/Taipei', run_id=f'run-{case}')
        assert len(gateway.requests) == 1
        assert result['analysis']['analysis_mode'] == 'llm'
        assert result['analysis']['input_fingerprint'] == result['evidence_fingerprint']
        if case == 'unplanned_activity':
            assert not result['yesterday']
            assert result['evidence_manifest']['sessions']
        else:
            assert result['yesterday'][0]['state'] == (
                'uncertain_prescription' if case == 'uncertain' else
                'completed' if case == 'completed_no_detail' else 'missed')
