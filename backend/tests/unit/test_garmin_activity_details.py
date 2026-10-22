"""Garmin JSON normalization uses descriptor positions and keeps overlap explicit."""
import json
from pathlib import Path

from src.infrastructure.integrations.garmin_activity_details import (
    normalize_activity_details, select_execution_evidence,
)

FIXTURES = Path(__file__).resolve().parents[1] / 'fixtures/activity_details'


def test_reordered_chart_descriptors_missing_hr_and_private_fields():
    payload = json.loads((FIXTURES / 'synthetic_details.json').read_text())
    result = normalize_activity_details(activity_id='local-activity', resource='details', payload=payload)
    assert result.coverage.sampling == 'chart'
    assert result.coverage.state == 'partial'
    assert len(result.sample_chunks) == 1
    points = result.sample_chunks[0].samples
    assert [point['timer_seconds'] for point in points] == [0, 1, 2]
    assert [point.get('heart_rate_bpm') for point in points] == [125, None, 130]
    serialized = json.dumps(result.to_payload())
    for private in ('PRIVATE', '121.55555', 'activityName', 'geoPolyline', 'session_data'):
        assert private not in serialized


def test_unknown_descriptor_unit_cannot_claim_complete_coverage():
    payload = {'metricDescriptors': [
        {'metricsIndex': 0, 'key': 'sumDuration', 'unit': {'key': 'alien', 'factor': 1}},
        {'metricsIndex': 1, 'key': 'directHeartRate', 'unit': {'key': 'bpm', 'factor': 1}},
    ], 'activityDetailMetrics': [{'metrics': [1000, 130]}]}
    result = normalize_activity_details(activity_id='a', resource='details', payload=payload)
    assert result.coverage.state != 'complete'
    assert 'elapsed_seconds' in result.coverage.missing_channels
    assert result.sample_chunks[0].samples[0].get('elapsed_seconds') is None


def test_observed_descriptor_values_are_already_in_physical_units():
    result = normalize_activity_details(activity_id='a', resource='details', payload={
        'metricDescriptors': [
            {'metricsIndex': 2, 'key': 'sumDistance', 'unit': {'key': 'meter', 'factor': 100}},
            {'metricsIndex': 0, 'key': 'sumDuration', 'unit': {'key': 'second', 'factor': 1000}},
            {'metricsIndex': 1, 'key': 'sumElapsedDuration', 'unit': {'key': 'second', 'factor': 1000}},
            {'metricsIndex': 3, 'key': 'directSpeed', 'unit': {'key': 'mps', 'factor': 0.1}},
        ], 'activityDetailMetrics': [{'metrics': [10, 12, 34, 2.5]}]})
    point = result.sample_chunks[0].samples[0]
    assert point['timer_seconds'] == 10
    assert point['elapsed_seconds'] == 12
    assert point['distance_meters'] == 34
    assert point['speed_mps'] == 2.5
    assert point['pace_seconds_per_km'] == 400
    assert result.source_payload['metric_units']['elapsed_seconds'] == {'unit': 'second', 'factor': 1000}
    assert result.coverage.state == 'partial'
    assert 'elapsed_seconds' not in result.coverage.missing_channels
    assert 'descriptor_scale_not_fit_verified' not in result.coverage.limitations
    assert select_execution_evidence((result,)).sample_resource == 'details'


def test_unobserved_chart_factor_does_not_claim_normalized_speed():
    result = normalize_activity_details(activity_id='a', resource='details', payload={
        'metricDescriptors': [
            {'metricsIndex': 0, 'key': 'sumElapsedDuration',
             'unit': {'key': 'second', 'factor': 1000}},
            {'metricsIndex': 1, 'key': 'directSpeed',
             'unit': {'key': 'mps', 'factor': 10}},
        ], 'activityDetailMetrics': [{'metrics': [10, 2.5]}]})
    assert result.sample_chunks[0].samples[0] == {'elapsed_seconds': 10}
    assert 'speed_mps' in result.coverage.missing_channels


def test_laps_preserve_timer_elapsed_and_auto_laps_have_no_step_path():
    payload = {'lapDTOs': [
        {'lapIndex': 2, 'startTimeGMT': '2026-10-22 08:10:00', 'duration': 590,
         'elapsedDuration': 650, 'distance': 1000, 'averageHR': None, 'averageSpeed': 0},
        {'lapIndex': 1, 'startTimeGMT': '2026-10-22 08:00:00', 'duration': 600,
         'elapsedDuration': 600, 'distance': 1000, 'averageHR': 135, 'averageSpeed': 2.5},
    ]}
    result = normalize_activity_details(activity_id='a', resource='splits', payload=payload)
    first, second = result.segments
    assert [segment.source_index for segment in result.segments] == [1, 0]
    assert first.timer_seconds == 600 and first.elapsed_seconds == 600
    assert second.timer_seconds == 590 and second.elapsed_seconds == 650
    assert second.average_pace_seconds_per_km is None
    assert first.average_pace_seconds_per_km == 400
    assert all(segment.step_path is None for segment in result.segments)


def test_typed_splits_and_summaries_do_not_add_to_lap_totals():
    laps = normalize_activity_details(activity_id='a', resource='splits', payload={
        'lapDTOs': [{'duration': 300, 'distance': 1000}, {'duration': 300, 'distance': 1000}]})
    typed = normalize_activity_details(activity_id='a', resource='typed_splits', payload={
        'splits': [{'duration': 600, 'distance': 2000, 'type': 'RUN'}]})
    summaries = normalize_activity_details(activity_id='a', resource='split_summaries', payload={
        'splitSummaries': [{'duration': 600, 'distance': 2000, 'splitType': 'RUN'}]})
    selected = select_execution_evidence((summaries, typed, laps))
    assert [segment.timer_seconds for segment in selected.segments] == [300, 300]
    assert sum(segment.distance_meters or 0 for segment in selected.segments) == 2000
    assert selected.segment_resource == 'splits'
    assert 'aggregate_not_additive' in summaries.coverage.limitations


def test_hr_zones_are_aggregate_context_not_workout_steps():
    result = normalize_activity_details(activity_id='a', resource='hr_zones', payload={
        'zones': [{'zoneNumber': 1, 'secsInZone': 120, 'zoneLowBoundary': 100}]})
    assert result.segments[0].source_kind == 'hr_zone_aggregate'
    assert result.segments[0].step_path is None
    assert result.segments[0].timer_seconds == 120
    assert result.coverage.state == 'partial'


def test_chart_limit_and_zero_speed_remain_partial():
    result = normalize_activity_details(activity_id='a', resource='details', payload={
        'metricDescriptors': [
            {'metricsIndex': 1, 'key': 'directSpeed', 'unit': {'key': 'mps', 'factor': 0.1}},
            {'metricsIndex': 0, 'key': 'sumDuration', 'unit': {'key': 's', 'factor': 1000}},
        ],
        'activityDetailMetrics': [{'metrics': [i, 0]} for i in range(2000)],
    })
    assert result.coverage.state == 'partial'
    assert 'chart_limit_reached' in result.coverage.limitations
    assert result.sample_chunks[0].samples[0].get('pace_seconds_per_km') is None
    assert len(result.sample_chunks[0].samples) == 2000
    assert select_execution_evidence((result,)).sample_resource is None


def test_malformed_or_duplicate_chart_descriptors_do_not_guess_channels():
    result = normalize_activity_details(activity_id='a', resource='details', payload={
        'metricDescriptors': [
            {'metricsIndex': 0, 'key': ['not-a-string'], 'unit': {'key': 'bpm', 'factor': 1}},
            {'metricsIndex': 0, 'key': 'directHeartRate', 'unit': {'key': 'bpm', 'factor': 1}},
            {'metricsIndex': 0, 'key': 'directSpeed', 'unit': {'key': 'mps', 'factor': 0.1}},
        ], 'activityDetailMetrics': [{'metrics': [140]}]})
    assert result.sample_chunks == ()
    assert result.coverage.state == 'unknown'
    assert 'heart_rate_bpm' in result.coverage.missing_channels
