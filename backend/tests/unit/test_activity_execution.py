"""Execution findings must distinguish measured steps from totals and sampled charts."""
from datetime import date, datetime, timedelta, timezone

from src.domain.activity_details import (
    ActivitySampleChunk, ActivitySegment, DetailCoverage, DetailSnapshot, NormalizedDetails,
)
from src.domain.activity_health import CompletedActivity
from src.domain.activity_execution import analyze_execution
from src.domain.training_plan import Workout, WorkoutStep, WorkoutTarget
from src.domain.training_review import PrescriptionSnapshot

START = datetime(2026, 10, 22, 23, 50, tzinfo=timezone.utc)


def prescription(*, steps=None, confidence='known'):
    steps = steps or (
        WorkoutStep.create(step_type='warmup', duration_seconds=600),
        WorkoutStep.create(step_type='work', duration_seconds=1200),
        WorkoutStep.create(step_type='cooldown', duration_seconds=300),
    )
    workout = Workout.create(id='workout', scheduled_for=date(2026, 10, 23),
                             workout_type='easy_run', purpose='Aerobic', steps=steps)
    return PrescriptionSnapshot('runner', 'plan', 'workout', workout,
                                START - timedelta(days=1), 'generation', confidence,
                                revision_id='revision-1')


def activity(*, identity='run', seconds=2640, started_at=START, matched='workout'):
    return CompletedActivity.create(id=identity, user_id='runner', source='manual',
        started_at=started_at, sport_type='running', duration_seconds=seconds,
        distance_meters=5000, matched_workout_id=matched, match_reviewed=True)


def snapshot(segments=(), *, activity_id='run', resource='fit', coverage='complete',
             sampling='recorded', chunks=()):
    normalized = NormalizedDetails(activity_id, resource, 'test-v1',
        DetailCoverage(coverage, sampling), tuple(segments), tuple(chunks))
    return DetailSnapshot(f'{activity_id}-{resource}', 'runner', normalized, 'hash', START)


def lap(index, seconds, *, step=None, occurrence=1, kind='fit_lap', start=0,
        trigger='manual', distance=1000, pace=360, planned=None):
    metadata = {'lap_trigger': trigger}
    if step is not None:
        metadata['repeat_occurrence'] = occurrence
        metadata['fit_planned_duration_seconds'] = planned if planned is not None else {0: 600, 1: 1200, 2: 300}.get(step)
    return ActivitySegment(source_index=index, source_kind=kind,
        start_at=START + timedelta(seconds=start),
        end_at=START + timedelta(seconds=start + seconds),
        timer_seconds=seconds, elapsed_seconds=seconds,
        distance_meters=distance, average_pace_seconds_per_km=pace,
        step_path=f'fit_step/{step}' if step is not None else None,
        metadata=metadata)


def fact(analysis, metric):
    return next(item for item in analysis.facts if item.metric == metric)


def test_35_to_44_minutes_identifies_cooldown_only_with_valid_explicit_step_link():
    data = snapshot((lap(0, 600, step=0, start=0),
                     lap(1, 1200, step=1, start=600),
                     lap(2, 840, step=2, start=1800)))
    result = analyze_execution(prescription=prescription(), activities=(activity(),), details=(data,))
    assert result.mapping == 'exact'
    assert [finding.code for finding in result.findings] == ['cooldown_volume_over']
    assert fact(result, 'duration_delta_seconds').value == 540
    step_delta = fact(result, 'step_duration_delta_seconds')
    assert (step_delta.value, step_delta.scope) == (540, '2#1')
    assert step_delta.id in result.findings[0].fact_ids
    assert result.prescription_revision_id == 'revision-1'
    assert result.snapshot_ids == ('run-fit',)
    assert result.fingerprint == analyze_execution(
        prescription=prescription(), activities=(activity(),), details=(data,)).fingerprint


def test_same_total_extension_in_work_is_a_different_finding():
    data = snapshot((lap(0, 600, step=0, start=0),
                     lap(1, 1740, step=1, start=600),
                     lap(2, 300, step=2, start=2340)))
    result = analyze_execution(prescription=prescription(), activities=(activity(),), details=(data,))
    assert [finding.code for finding in result.findings] == ['work_volume_over']


def test_auto_lap_and_ambiguous_timeline_never_claim_exact_step_or_cause():
    auto = snapshot((lap(0, 600, start=0, trigger='distance'),
                     lap(1, 1200, start=600, trigger='distance'),
                     lap(2, 840, start=1800, trigger='distance')))
    result = analyze_execution(prescription=prescription(), activities=(activity(),), details=(auto,))
    assert result.mapping != 'exact'
    assert not any(item.code in {'cooldown_volume_over', 'work_volume_over'} for item in result.findings)
    ambiguous = snapshot((lap(0, 600, start=0), lap(1, 600, start=0)))
    assert analyze_execution(prescription=prescription(), activities=(activity(),),
                             details=(ambiguous,)).mapping == 'unmatched'


def test_repeat_occurrence_is_part_of_identity_and_missing_repeat_is_reported():
    steps = (WorkoutStep.create(step_type='repeat', repeat_count=3, steps=(
        WorkoutStep.create(step_type='work', duration_seconds=300),
        WorkoutStep.create(step_type='recovery', duration_seconds=120),
    )),)
    runs = (lap(0, 300, step=0, occurrence=1, start=0, planned=300),
            lap(1, 120, step=1, occurrence=1, start=300, planned=120),
            lap(2, 300, step=0, occurrence=2, start=420, planned=300),
            lap(3, 120, step=1, occurrence=2, start=720, planned=120))
    result = analyze_execution(prescription=prescription(steps=steps),
        activities=(activity(seconds=840),), details=(snapshot(runs),))
    assert any(item.code == 'missed_repeat' for item in result.findings)
    identities = [item.scope for item in result.facts if item.metric == 'step_timer_seconds']
    assert len(set(identities)) == 4


def test_unmatched_tail_and_two_recording_gap_are_not_assigned_to_work_step():
    first = activity(identity='a', seconds=1200)
    second = activity(identity='b', seconds=1440, started_at=START + timedelta(seconds=1800))
    data = (snapshot((lap(0, 600, step=0), lap(1, 600, step=1, start=600)), activity_id='a'),
            snapshot((lap(0, 900, step=1), lap(1, 300, step=2, start=900),
                      lap(2, 240, start=1200)), activity_id='b'))
    result = analyze_execution(prescription=prescription(), activities=(first, second), details=data)
    assert result.mapping != 'exact'
    assert any(item.code == 'unmatched_tail' for item in result.findings)
    assert fact(result, 'unmatched_timer_seconds').value == 240
    assert 'recording_gap' in result.limitations


def test_chart_and_unknown_historical_target_do_not_create_interval_compliance():
    target = WorkoutTarget.pace(zone='easy')
    planned = prescription(steps=(WorkoutStep.create(step_type='work',
        duration_seconds=600, target=target),))
    chart = snapshot(resource='details', coverage='partial', sampling='chart',
        chunks=(ActivitySampleChunk(0, ({'elapsed_seconds': 0, 'pace_seconds_per_km': 350},
                                      {'elapsed_seconds': 60, 'pace_seconds_per_km': 355})),))
    result = analyze_execution(prescription=planned, activities=(activity(seconds=600),), details=(chart,))
    assert not any(item.metric == 'target_time_seconds' for item in result.facts)
    assert 'sampled_chart' in result.limitations
    assert 'historical_target_range_missing' in result.limitations


def test_uncertain_prescription_and_dst_local_date_only_support_session_totals():
    at = datetime(2026, 11, 1, 1, 30, tzinfo=timezone(timedelta(hours=-4)))
    uncertain = prescription(confidence='legacy_uncertain')
    data = snapshot((lap(0, 2640, step=0),))
    result = analyze_execution(prescription=uncertain,
        activities=(activity(started_at=at),), details=(data,))
    assert result.mapping == 'unmatched'
    assert fact(result, 'actual_timer_seconds').value == 2640
    assert 'uncertain_prescription' in result.limitations


def test_partial_segments_use_summary_for_total_delta_and_label_recorded_coverage():
    data = snapshot((lap(0, 600, step=0),), coverage='partial')
    result = analyze_execution(prescription=prescription(), activities=(activity(),), details=(data,))
    assert fact(result, 'duration_delta_seconds').value == 540
    assert fact(result, 'recorded_timer_seconds').value == 600
    assert 'partial_detail_coverage' in result.limitations


def test_recorded_target_time_excludes_pause_and_sample_gap_and_exposes_denominator():
    target = WorkoutTarget.pace(zone='easy', pace_range_seconds_per_km=(330, 370))
    planned = prescription(steps=(WorkoutStep.create(step_type='work',
        duration_seconds=60, target=target),))
    segment = lap(0, 60, step=0, planned=60)
    rows = ({'at': START.isoformat(), 'timer_running': True, 'pace_seconds_per_km': 350},
            {'at': (START + timedelta(seconds=10)).isoformat(), 'timer_running': True,
             'pace_seconds_per_km': 350},
            {'at': (START + timedelta(seconds=20)).isoformat(), 'timer_running': False,
             'pace_seconds_per_km': 350},
            {'at': (START + timedelta(seconds=55)).isoformat(), 'timer_running': True,
             'pace_seconds_per_km': 350})
    data = snapshot((segment,), chunks=(ActivitySampleChunk(0, rows),))
    result = analyze_execution(prescription=planned, activities=(activity(seconds=60),), details=(data,))
    target_fact = fact(result, 'target_time_seconds')
    assert (target_fact.value, target_fact.covered_seconds, target_fact.denominator_seconds) == (10, 10, 60)
    assert 'target_interval_coverage_partial' in result.limitations


def test_input_fingerprint_changes_when_snapshot_content_changes():
    first = snapshot((lap(0, 600, step=0),))
    revised = DetailSnapshot(first.id, first.user_id, first.details, 'changed-hash', first.fetched_at)
    a = analyze_execution(prescription=prescription(), activities=(activity(),), details=(first,))
    b = analyze_execution(prescription=prescription(), activities=(activity(),), details=(revised,))
    assert a.fingerprint != b.fingerprint


def test_auto_laps_have_no_unmatched_tail_without_an_actual_tail():
    auto = snapshot((lap(0, 600, start=0), lap(1, 1200, start=600),
                     lap(2, 840, start=1800)))
    result = analyze_execution(prescription=prescription(), activities=(activity(),), details=(auto,))
    assert not any(item.code == 'unmatched_tail' for item in result.findings)


def test_exact_segment_reports_distance_delta_without_additive_overlap():
    steps = (WorkoutStep.create(step_type='work', duration_seconds=600, distance_meters=1000),)
    result = analyze_execution(prescription=prescription(steps=steps),
        activities=(activity(seconds=600),),
        details=(snapshot((lap(0, 600, step=0, distance=1200),)),))
    assert fact(result, 'step_distance_delta_meters').value == 200


def test_fit_step_index_alone_cannot_validate_a_changed_historical_prescription():
    changed = prescription(steps=(WorkoutStep.create(step_type='warmup', duration_seconds=700),
                                  WorkoutStep.create(step_type='work', duration_seconds=1100),
                                  WorkoutStep.create(step_type='cooldown', duration_seconds=300)))
    data = snapshot((lap(0, 600, step=0), lap(1, 1200, step=1, start=600),
                     lap(2, 840, step=2, start=1800)))
    result = analyze_execution(prescription=changed, activities=(activity(),), details=(data,))
    assert result.mapping != 'exact'
    assert not any(item.code == 'cooldown_volume_over' for item in result.findings)


def test_unique_ordered_distance_boundaries_are_estimated_not_exact():
    steps = (WorkoutStep.create(step_type='warmup', distance_meters=1000),
             WorkoutStep.create(step_type='work', distance_meters=2000))
    data = snapshot((lap(0, 400, start=0, distance=1000, trigger='distance'),
                     lap(1, 800, start=400, distance=2000, trigger='distance')))
    result = analyze_execution(prescription=prescription(steps=steps),
        activities=(activity(seconds=1200),), details=(data,))
    assert result.mapping == 'estimated'
    assert 'ordered_boundary_estimate_not_step_identity' in result.limitations
    assert not any(item.metric == 'step_timer_seconds' for item in result.facts)


def test_forged_fit_step_marker_on_json_lap_does_not_claim_exact_mapping():
    data = snapshot((lap(0, 600, step=0), lap(1, 1200, step=1, start=600),
                     lap(2, 840, step=2, start=1800)), resource='splits')
    result = analyze_execution(prescription=prescription(), activities=(activity(),), details=(data,))
    assert result.mapping != 'exact'


def test_latest_snapshot_revision_is_used_when_history_contains_older_fit():
    older = snapshot((lap(0, 600, step=0),))
    newer = DetailSnapshot('run-fit-new', older.user_id,
        NormalizedDetails('run', 'fit', 'test-v1', DetailCoverage('complete', 'recorded'),
            (lap(0, 600, step=0), lap(1, 1200, step=1, start=600),
             lap(2, 840, step=2, start=1800))),
        'new-hash', START + timedelta(hours=1))
    result = analyze_execution(prescription=prescription(), activities=(activity(),),
                               details=(older, newer))
    assert result.snapshot_ids == ('run-fit-new',)
    assert [finding.code for finding in result.findings] == ['cooldown_volume_over']


def test_repeated_equal_unlinked_boundaries_remain_unmatched():
    steps = (WorkoutStep.create(step_type='work', duration_seconds=300),
             WorkoutStep.create(step_type='recovery', duration_seconds=300))
    data = snapshot((lap(0, 300, start=0), lap(1, 300, start=300)))
    result = analyze_execution(prescription=prescription(steps=steps),
        activities=(activity(seconds=600),), details=(data,))
    assert result.mapping == 'unmatched'


def test_missing_historical_revision_id_does_not_authorize_exact_step_claim():
    from dataclasses import replace
    unversioned = replace(prescription(), revision_id=None)
    data = snapshot((lap(0, 600, step=0), lap(1, 1200, step=1, start=600),
                     lap(2, 840, step=2, start=1800)))
    result = analyze_execution(prescription=unversioned, activities=(activity(),), details=(data,))
    assert result.mapping != 'exact'
    assert 'prescription_revision_missing' in result.limitations


def test_distance_only_prescription_reports_session_distance_delta():
    race = Workout.create(id='workout', scheduled_for=date(2026, 10, 23),
        workout_type='race', purpose='10K', planned_distance_meters=10000,
        race_goal_id='goal', race_name='10K', race_priority='primary')
    planned = PrescriptionSnapshot('runner', 'plan', 'workout', race,
        START - timedelta(days=1), 'generation', 'known', revision_id='revision-1')
    result = analyze_execution(prescription=planned, activities=(activity(),), details=())
    assert fact(result, 'distance_delta_meters').value == -5000
    assert not any(item.metric == 'duration_delta_seconds' for item in result.facts)
