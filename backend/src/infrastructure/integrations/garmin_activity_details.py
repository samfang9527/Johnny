"""Conservative normalization of Garmin Connect JSON activity detail resources.

These endpoints describe overlapping views of one activity. Their rows must not be
added together as if they were disjoint time intervals.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from math import isfinite
from typing import Any

from src.domain.activity_details import (
    ActivitySampleChunk, ActivitySegment, DetailCoverage, DetailResource, NormalizedDetails,
)

# Three owned Garmin chart/FIT pairs confirmed that chart values are already in
# seconds, meters, m/s and bpm. The descriptor factor is a shape guard, not a
# multiplier or divisor for these observed metric/unit combinations.
SCHEMA_VERSION = 'garmin-json-v2'
_METRIC_CHANNELS = {
    'sumDuration': ('timer_seconds', {'s', 'second'}, 1000.0),
    'sumElapsedDuration': ('elapsed_seconds', {'s', 'second'}, 1000.0),
    'sumDistance': ('distance_meters', {'m', 'meter'}, 100.0),
    'directHeartRate': ('heart_rate_bpm', {'bpm'}, 1.0),
    'directSpeed': ('speed_mps', {'mps'}, 0.1),
}


@dataclass(frozen=True)
class SelectedExecutionEvidence:
    segments: tuple[ActivitySegment, ...]
    sample_chunks: tuple[ActivitySampleChunk, ...]
    segment_resource: DetailResource | None
    sample_resource: DetailResource | None


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value):
        return None
    return float(value)


def _utc(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        except ValueError:
            return None
    else:
        return None
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)


def _pace(speed: float | None) -> float | None:
    return 1000.0 / speed if speed is not None and speed > 0 else None


def _rows(payload: dict, key: str) -> list[dict]:
    value = payload.get(key)
    return [row for row in value if isinstance(row, dict)] if isinstance(value, list) else []


def _segment(row: dict, index: int, kind: str) -> ActivitySegment:
    timer = _number(row.get('duration'))
    elapsed = _number(row.get('elapsedDuration'))
    distance = _number(row.get('distance'))
    start = _utc(row.get('startTimeGMT'))
    end = _utc(row.get('endTimeGMT'))
    if start is None and end is not None and elapsed is not None:
        start = end - timedelta(seconds=elapsed)
    if end is None and start is not None and elapsed is not None:
        end = start + timedelta(seconds=elapsed)
    metadata: dict[str, Any] = {}
    for source, target in (('lapIndex', 'lap_index'), ('messageIndex', 'message_index')):
        value = row.get(source)
        if isinstance(value, int) and not isinstance(value, bool):
            metadata[target] = value
    intensity = row.get('intensityType') or row.get('type') or row.get('splitType')
    if isinstance(intensity, str) and intensity.upper() in {
        'WARMUP', 'ACTIVE', 'RECOVERY', 'COOLDOWN', 'RUN', 'WALK', 'INTERVAL', 'REST',
    }:
        metadata['intensity_type'] = intensity.upper()
    return ActivitySegment(source_index=index, source_kind=kind, start_at=start, end_at=end,
                           timer_seconds=timer, elapsed_seconds=elapsed, distance_meters=distance,
                           average_heart_rate_bpm=_number(row.get('averageHR')),
                           average_pace_seconds_per_km=_pace(_number(row.get('averageSpeed'))),
                           metadata=metadata)


def _segment_resource(activity_id: str, resource: DetailResource, payload: dict) -> NormalizedDetails:
    key, kind = {
        'splits': ('lapDTOs', 'garmin_lap'),
        'typed_splits': ('splits', 'typed_split'),
        'split_summaries': ('splitSummaries', 'split_summary_aggregate'),
    }[resource]
    rows = _rows(payload, key)
    segments = tuple(sorted((_segment(row, index, kind) for index, row in enumerate(rows)),
                            key=lambda segment: (segment.start_at is None,
                                                 segment.start_at or datetime.max.replace(tzinfo=timezone.utc),
                                                 segment.source_index)))
    limitations = ['no_explicit_workout_step_link']
    if resource == 'split_summaries':
        limitations.append('aggregate_not_additive')
    elif resource == 'typed_splits':
        limitations.append('typed_split_overlap_unverified')
    return NormalizedDetails(activity_id=activity_id, resource=resource, schema_version=SCHEMA_VERSION,
        coverage=DetailCoverage(state='partial' if segments else 'unknown', sampling='unknown',
            covered_seconds=sum(segment.timer_seconds or 0 for segment in segments)
                            if resource == 'splits' and segments else None,
            limitations=tuple(limitations)), segments=segments, source_payload={'row_count': len(rows)})


def _chart(activity_id: str, payload: dict) -> NormalizedDetails:
    descriptors = _rows(payload, 'metricDescriptors')
    rows = _rows(payload, 'activityDetailMetrics')
    indexes: dict[int, str] = {}
    blocked_indexes: set[int] = set()
    rejected: set[str] = set()
    unit_metadata: dict[str, dict] = {}
    for descriptor in descriptors:
        key = descriptor.get('key')
        if not isinstance(key, str) or key not in _METRIC_CHANNELS:
            continue
        channel, units, factor = _METRIC_CHANNELS[key]
        index = descriptor.get('metricsIndex')
        descriptor_unit = descriptor.get('unit')
        actual_unit = descriptor_unit.get('key') if isinstance(descriptor_unit, dict) else None
        actual_factor = _number(descriptor_unit.get('factor')) if isinstance(descriptor_unit, dict) else None
        if (not isinstance(index, int) or isinstance(index, bool) or index < 0
                or actual_unit not in units or actual_factor != factor):
            rejected.add(channel)
            continue
        if index in blocked_indexes:
            rejected.add(channel)
            continue
        if index in indexes:
            previous = indexes.pop(index)
            rejected.add(previous)
            rejected.add(channel)
            unit_metadata.pop(previous, None)
            blocked_indexes.add(index)
            continue
        indexes[index] = channel
        unit_metadata[channel] = {'unit': actual_unit, 'factor': factor}
    samples: list[dict[str, Any]] = []
    for row in (rows if indexes else ()):
        values = row.get('metrics')
        if not isinstance(values, list):
            continue
        sample: dict[str, Any] = {}
        for index, channel in indexes.items():
            if index < len(values) and (value := _number(values[index])) is not None:
                sample[channel] = value
        if (speed := sample.get('speed_mps')) is not None and speed > 0:
            sample['pace_seconds_per_km'] = 1000 / speed
        samples.append(sample)
    chunks = tuple(ActivitySampleChunk(ordinal=index // 2000, samples=tuple(samples[index:index + 2000]))
                   for index in range(0, len(samples), 2000))
    observed = {channel for sample in samples for channel in sample}
    missing_set = rejected | ({'timer_seconds', 'elapsed_seconds', 'distance_meters',
                               'speed_mps', 'heart_rate_bpm'} - observed)
    missing = tuple(sorted(missing_set))
    limitations = ['chart_sampling_not_recorded']
    if len(rows) >= 2000:
        limitations.append('chart_limit_reached')
    return NormalizedDetails(activity_id=activity_id, resource='details', schema_version=SCHEMA_VERSION,
        coverage=DetailCoverage(state='partial' if samples else 'unknown', sampling='chart',
            missing_channels=missing, limitations=tuple(limitations)),
        sample_chunks=chunks, source_payload={'chart_point_count': len(rows),
                                               'metric_units': unit_metadata})


def _hr_zones(activity_id: str, payload: dict) -> NormalizedDetails:
    zones = _rows(payload, 'zones')
    segments = []
    for index, zone in enumerate(zones):
        number = zone.get('zoneNumber')
        if not isinstance(number, int) or isinstance(number, bool):
            continue
        metadata: dict[str, Any] = {'zone_number': number}
        if (floor := _number(zone.get('zoneLowBoundary'))) is not None:
            metadata['zone_low_boundary_bpm'] = floor
        segments.append(ActivitySegment(source_index=index, source_kind='hr_zone_aggregate',
                                        timer_seconds=_number(zone.get('secsInZone')), metadata=metadata))
    return NormalizedDetails(activity_id=activity_id, resource='hr_zones', schema_version=SCHEMA_VERSION,
        coverage=DetailCoverage(state='partial' if segments else 'unknown', sampling='unknown',
                                limitations=('aggregate_not_step_level',)),
        segments=tuple(segments), source_payload={'zone_count': len(zones)})


def normalize_activity_details(*, activity_id: str, resource: DetailResource, payload: dict) -> NormalizedDetails:
    if not isinstance(payload, dict):
        raise ValueError('activity detail payload must be an object')
    if resource in ('splits', 'typed_splits', 'split_summaries'):
        return _segment_resource(activity_id, resource, payload)
    if resource == 'details':
        return _chart(activity_id, payload)
    if resource == 'hr_zones':
        return _hr_zones(activity_id, payload)
    raise ValueError(f'unsupported JSON detail resource: {resource}')


def select_execution_evidence(details: tuple[NormalizedDetails, ...]) -> SelectedExecutionEvidence:
    """Choose one source per overlapping channel; retain provenance for analysis."""
    priority = {'fit': 0, 'splits': 1, 'typed_splits': 2, 'split_summaries': 3}
    segment_sources = [item for item in details if item.resource in priority and item.segments
                       and item.coverage.state != 'unknown']
    segment_source = min(segment_sources, key=lambda item: priority[item.resource]) if segment_sources else None
    sample_sources = [item for item in details if item.resource in ('fit', 'details') and item.sample_chunks
                      and item.coverage.state != 'unknown' and any(
                          'elapsed_seconds' in sample for chunk in item.sample_chunks for sample in chunk.samples)]
    sample_source = min(sample_sources, key=lambda item: 0 if item.resource == 'fit' else 1) if sample_sources else None
    return SelectedExecutionEvidence(segments=segment_source.segments if segment_source else (),
        sample_chunks=sample_source.sample_chunks if sample_source else (),
        segment_resource=segment_source.resource if segment_source else None,
        sample_resource=sample_source.resource if sample_source else None)
