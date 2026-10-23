from dataclasses import replace
from datetime import date, datetime, timezone

from src.application.coaching_analysis_evidence import AdviceContext, build_coaching_evidence, coaching_manifest_fingerprint
from src.domain.activity_health import DailyHealthMetrics
from src.domain.activity_execution import ExecutionAnalysis, ExecutionFinding
from src.domain.training_plan import TrainingPlan, Workout, WorkoutStep
from src.domain.training_review import ReviewEvidence, review_period
from src.domain.workout_advice import WorkoutAdviceConstraints


DAY = date(2027, 1, 16)
NOW = datetime(2027, 1, 15, 23, tzinfo=timezone.utc)


class Store:
    def __init__(self):
        self.metrics = ()
        self.analyses = ()
        self.snapshots = ()
        self.workout = Workout.create(id='w', scheduled_for=DAY, workout_type='easy_run',
                                      purpose='Easy', planned_duration_minutes=35,
                                      steps=(WorkoutStep.create(step_type='free_run',
                                                                duration_seconds=2100),))
        self.plan = TrainingPlan.create(id='p', user_id='u', name='Base', starts_on=DAY,
                                        ends_on=DAY, workouts=(self.workout,))
        self.fetched_at = 'first'
        self.coverage = frozenset()

    def load_review_evidence(self, user_id, publication_date, timezone_name, as_of):
        return ReviewEvidence(review_period(publication_date), timezone_name, as_of,
                              (), (), self.coverage)

    def load_advice_context(self, user_id, local_date, timezone_name, workout_id, as_of):
        return AdviceContext(self.plan, self.workout, (), None, ())

    def list_execution_analyses(self, user_id, starts_on, ends_on, as_of):
        return self.analyses

    def list_recovery_metrics(self, user_id, starts_on, ends_on):
        return self.metrics

    def list_current_detail_snapshots(self, user_id, starts_on, ends_on, as_of):
        return self.snapshots


def build(store, kind='workout_advice'):
    return build_coaching_evidence(user_id='u', kind=kind, local_date=DAY,
                                   timezone_name='Asia/Taipei', workout_id='w' if kind == 'workout_advice' else None,
                                   constraints=WorkoutAdviceConstraints() if kind == 'workout_advice' else None,
                                   as_of=NOW, store=store)


def test_advice_fingerprint_tracks_used_values_not_fetch_metadata():
    store = Store()
    before = build(store)
    store.fetched_at = 'later'
    assert build(store).fingerprint == before.fingerprint
    store.workout = replace(store.workout, planned_duration_minutes=36,
                            steps=(WorkoutStep.create(step_type='free_run',
                                                      duration_seconds=2160),))
    assert build(store).fingerprint != before.fingerprint
    store.workout = Store().workout
    store.metrics = (DailyHealthMetrics.create(user_id='u', metric_date=DAY,
                                               sleep_duration_minutes=480),)
    assert build(store).fingerprint != before.fingerprint


def test_dated_signals_preserve_yesterday_and_do_not_change_today_readiness():
    store = Store()
    store.metrics = (
        DailyHealthMetrics.create(user_id='u', metric_date=DAY, sleep_duration_minutes=480),
        DailyHealthMetrics.create(user_id='u', metric_date=date(2027, 1, 15),
                                  hrv_ms=48, hrv_baseline_ms=50, stress_score=80),
        DailyHealthMetrics.create(user_id='other', metric_date=DAY, body_battery_score=1),
        DailyHealthMetrics.create(user_id='u', metric_date=date(2027, 1, 17), body_battery_score=1),
    )
    bundle = build(store)
    assert bundle.manifest['recovery']['readiness_label'] == 'unknown'
    assert bundle.manifest['recovery']['latest_signals']['sleep']['date'] == DAY.isoformat()
    assert bundle.manifest['recovery']['latest_signals']['hrv']['date'] == '2027-01-15'
    assert bundle.manifest['recovery']['latest_signals']['stress']['quality'] == 'previous_day'
    assert bundle.manifest['recovery']['latest_signals']['body_battery'] is None
    assert 'today_readiness' in bundle.manifest['action']['missing_facts']
    assert 'previous_day_recovery' in bundle.manifest['action']['available_facts']


def test_zero_hrv_baseline_is_missing_and_partial_stress_is_dated():
    store = Store()
    store.metrics = (DailyHealthMetrics.create(user_id='u', metric_date=DAY,
                    hrv_ms=48, hrv_baseline_ms=0, stress_score=70),)
    latest = build(store).manifest['recovery']['latest_signals']
    assert latest['hrv'] is None
    assert latest['stress']['quality'] == 'partial_current_day'


def test_review_period_coverage_and_unreferenced_analysis():
    store = Store()
    before = build(store, 'daily_review')
    assert before.manifest['periods']['reviewed_date'] == '2027-01-15'
    assert before.manifest['periods']['starts_on'] == '2027-01-09'
    assert before.manifest['coverage']['missing_dates']
    assert 'complete_activity_coverage' in before.manifest['action']['missing_facts']
    store.coverage = frozenset({date(2027, 1, 15)})
    assert build(store, 'daily_review').fingerprint != before.fingerprint
    store.analyses = (ExecutionAnalysis('unrelated', ('unrelated',), 'hash', None, (), 'unmatched',
                      (), (ExecutionFinding('x', (), 'a', 'b'),), ('uncertain',)),)
    assert build(store, 'daily_review').fingerprint == build(StoreWithCoverage(store.coverage), 'daily_review').fingerprint


class StoreWithCoverage(Store):
    def __init__(self, coverage):
        super().__init__()
        self.coverage = coverage


def test_advice_no_plan_and_completed_are_distinct():
    store = Store()
    planned = build(store)
    store.workout = replace(store.workout, status='completed')
    completed = build(store)
    assert completed.manifest['action']['state'] == 'completed'
    assert completed.fingerprint != planned.fingerprint
    store.workout = None
    store.plan = None
    assert build(store).manifest['action']['state'] == 'no_plan'
    store.plan = Store().plan
    assert build(store).manifest['action']['state'] == 'rest_day'


def test_history_uses_local_dates_and_bounds_findings_without_dropping_uncertainty():
    store = Store()
    analysis = ExecutionAnalysis('a', ('a',), 'content', 'revision', ('snapshot',), 'estimated', (),
        tuple(ExecutionFinding(f'finding-{i}', (), 'supported', 'not supported') for i in range(5)),
        ('partial_detail_coverage',), activity_started_at=datetime(2027, 1, 15, 15, 30,
                                                                  tzinfo=timezone.utc))
    store.analyses = (analysis,)
    manifest = build(store).manifest
    assert len(manifest['recent_analyses'][0]['findings']) == 3
    assert manifest['recent_analyses'][0]['omitted_finding_count'] == 2
    assert manifest['recent_analyses'][0]['limitations'] == ['partial_detail_coverage']
    assert 'samples' not in str(manifest).lower()
    assert 'gps' not in str(manifest).lower()
    store.analyses = (replace(analysis, activity_started_at=datetime(2027, 1, 15, 16, 30,
                                                                     tzinfo=timezone.utc)),)
    assert build(store).manifest['recent_analyses'] == []


def test_used_historical_analysis_changes_fingerprint():
    store = Store()
    first = build(store)
    store.analyses = (ExecutionAnalysis('a', ('a',), 'content-one', None, (),
        'unmatched', (), (), ('missing_prescription',),
        activity_started_at=datetime(2027, 1, 15, 15, tzinfo=timezone.utc)),)
    second = build(store)
    assert second.fingerprint != first.fingerprint
    store.analyses = (replace(store.analyses[0], fingerprint='content-two'),)
    assert build(store).fingerprint != second.fingerprint


def test_analysis_id_is_available_for_historical_evidence_without_changing_content_fingerprint():
    store = Store()
    analysis = ExecutionAnalysis('a', ('a',), 'content', None, (), 'unmatched', (), (), (),
        activity_started_at=datetime(2027, 1, 15, 15, tzinfo=timezone.utc), analysis_id='version-one')
    store.analyses = (analysis,)
    first = build(store)
    assert first.manifest['recent_analyses'][0]['analysis_id'] == 'version-one'
    store.analyses = (replace(analysis, analysis_id='version-two'),)
    second = build(store)
    assert second.manifest['recent_analyses'][0]['analysis_id'] == 'version-two'
    assert first.fingerprint == second.fingerprint
    assert coaching_manifest_fingerprint(first.manifest) == first.fingerprint
    assert coaching_manifest_fingerprint(second.manifest) == second.fingerprint


def test_committed_detail_pointer_invalidates_advice_before_analysis_batch_finishes():
    store = Store()
    before = build(store)
    started = datetime(2027, 1, 15, 15, tzinfo=timezone.utc)
    store.snapshots = ({'activity_id': 'a', 'resource': 'fit',
                        'snapshot_id': 's1', 'started_at': started},)
    first = build(store)
    assert first.fingerprint != before.fingerprint
    store.snapshots = ({**store.snapshots[0], 'snapshot_id': 's2'},)
    assert build(store).fingerprint != first.fingerprint
