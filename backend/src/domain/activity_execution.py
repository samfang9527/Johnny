"""Conservative, traceable comparison with the effective Workout Steps."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json

from src.domain.activity_details import ActivitySegment, DetailSnapshot
from src.domain.activity_health import CompletedActivity
from src.domain.training_plan import WorkoutStep
from src.domain.training_review import PrescriptionSnapshot

ALGORITHM_VERSION = 'execution-analysis-v1'


@dataclass(frozen=True)
class ExecutionFact:
    id: str
    metric: str
    value: float
    unit: str
    scope: str
    evidence_refs: tuple[str, ...]
    denominator_seconds: float | None = None
    covered_seconds: float | None = None

    def to_payload(self) -> dict:
        return dict(id=self.id, metric=self.metric, value=self.value, unit=self.unit,
                    scope=self.scope, evidence_refs=list(self.evidence_refs),
                    denominator_seconds=self.denominator_seconds,
                    covered_seconds=self.covered_seconds)


@dataclass(frozen=True)
class ExecutionFinding:
    code: str
    fact_ids: tuple[str, ...]
    supports: str
    does_not_support: str

    def to_payload(self) -> dict:
        return dict(code=self.code, fact_ids=list(self.fact_ids), supports=self.supports,
                    does_not_support=self.does_not_support)


@dataclass(frozen=True)
class ExecutionAnalysis:
    activity_id: str
    activity_ids: tuple[str, ...]
    fingerprint: str
    prescription_revision_id: str | None
    snapshot_ids: tuple[str, ...]
    mapping: str
    facts: tuple[ExecutionFact, ...]
    findings: tuple[ExecutionFinding, ...]
    limitations: tuple[str, ...]
    algorithm_version: str = ALGORITHM_VERSION
    activity_started_at: datetime | None = None

    def to_payload(self) -> dict:
        return dict(activity_id=self.activity_id, activity_ids=list(self.activity_ids),
                    fingerprint=self.fingerprint, prescription_revision_id=self.prescription_revision_id,
                    snapshot_ids=list(self.snapshot_ids), mapping=self.mapping,
                    facts=[fact.to_payload() for fact in self.facts],
                    findings=[finding.to_payload() for finding in self.findings],
                    limitations=list(self.limitations), algorithm_version=self.algorithm_version)


@dataclass(frozen=True)
class _Step:
    path: str
    occurrence: int
    fit_index: int
    step: WorkoutStep

    @property
    def scope(self) -> str:
        return f'{self.path}#{self.occurrence}'


def _expand(steps: tuple[WorkoutStep, ...]) -> tuple[_Step, ...]:
    indices: dict[str, int] = {}
    occurrences: dict[str, int] = {}
    expanded = []

    def visit(items, prefix=''):
        for position, step in enumerate(items):
            path = f'{prefix}/{position}' if prefix else str(position)
            if step.step_type == 'repeat':
                for _ in range(step.repeat_count or 0):
                    visit(step.steps, path)
            else:
                if path not in indices:
                    indices[path] = len(indices)
                occurrences[path] = occurrences.get(path, 0) + 1
                expanded.append(_Step(path, occurrences[path], indices[path], step))

    visit(steps)
    return tuple(expanded)


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _fingerprint(prescription, activities, snapshots):
    payload = dict(algorithm=ALGORITHM_VERSION,
        prescription=dict(revision_id=prescription.revision_id,
                          workout=prescription.workout.to_payload(), confidence=prescription.confidence,
                          effective_at=_utc(prescription.effective_at).isoformat()) if prescription else None,
        activities=[(a.id, _utc(a.started_at).isoformat(), a.duration_seconds,
                     a.distance_meters, a.matched_workout_id) for a in activities],
        snapshots=[(s.id, s.semantic_hash) for s in snapshots])
    return sha256(json.dumps(payload, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def _selected_segments(snapshots: tuple[DetailSnapshot, ...], activity_id: str):
    priority = {'fit': 0, 'splits': 1, 'typed_splits': 2, 'split_summaries': 3}
    sources = [s for s in snapshots if s.activity_id == activity_id and s.resource in priority
               and s.segments and s.details.coverage.state != 'unknown']
    chosen = min(sources, key=lambda s: priority[s.resource]) if sources else None
    return tuple((chosen, segment) for segment in chosen.segments) if chosen else ()


def analyze_execution(*, prescription: PrescriptionSnapshot | None,
                      activities: tuple[CompletedActivity, ...],
                      details: tuple[DetailSnapshot, ...]) -> ExecutionAnalysis:
    if not activities or any(a.id is None for a in activities):
        raise ValueError('persisted activities required')
    owners = {a.user_id for a in activities}
    activity_ids = {a.id for a in activities}
    if len(owners) != 1 or any(s.user_id not in owners or s.activity_id not in activity_ids for s in details):
        raise ValueError('detail ownership mismatch')
    ordered = tuple(sorted(activities, key=lambda a: (_utc(a.started_at), a.id or '')))
    current: dict[tuple[str, str], DetailSnapshot] = {}
    for candidate in details:
        key = (candidate.activity_id, candidate.resource)
        previous = current.get(key)
        if previous is None or (_utc(candidate.fetched_at), candidate.id) > (
                _utc(previous.fetched_at), previous.id):
            current[key] = candidate
    snapshots = tuple(current[key] for key in sorted(current))
    refs = tuple(s.id for s in snapshots)
    segments = tuple((source, segment) for a in ordered for source, segment in
                     _selected_segments(snapshots, a.id))
    facts: list[ExecutionFact] = []
    findings: list[ExecutionFinding] = []
    limitations: list[str] = []

    def fact(metric, value, unit='s', scope='session', evidence=refs, denominator=None, covered=None):
        item = ExecutionFact(f'f{len(facts) + 1}', metric, value, unit, scope,
                             tuple(evidence), denominator, covered)
        facts.append(item)
        return item

    def finding(code, source, supports, excludes):
        cited = source if isinstance(source, tuple) else (source,)
        findings.append(ExecutionFinding(code, tuple(item.id for item in cited), supports, excludes))

    recorded = sum(segment.timer_seconds or 0 for _, segment in segments)
    summary = sum(a.duration_seconds for a in ordered)
    complete_timer = recorded > 0 and abs(recorded - summary) <= 5 and all(
        source.resource == 'fit' and source.details.coverage.state == 'complete'
        for source, _ in segments)
    actual = recorded if complete_timer else summary
    fact('actual_timer_seconds' if complete_timer else 'actual_duration_seconds', actual,
         evidence=refs or tuple(a.id for a in ordered))
    if recorded > 0 and not complete_timer:
        fact('recorded_timer_seconds', recorded, evidence=refs)
    actual_distance = sum(a.distance_meters for a in ordered)
    fact('actual_distance_meters', actual_distance, 'm',
         evidence=tuple(a.id for a in ordered))
    if len(ordered) > 1 and any(
        (_utc(right.started_at) - _utc(left.started_at) - timedelta(seconds=left.duration_seconds)).total_seconds() > 30
        for left, right in zip(ordered, ordered[1:])):
        limitations.append('recording_gap')
    if any(s.details.coverage.sampling == 'chart' for s in snapshots):
        limitations.append('sampled_chart')
    if any(s.details.coverage.state != 'complete' for s in snapshots):
        limitations.append('partial_detail_coverage')
    known = bool(prescription and prescription.confidence == 'known' and
                 prescription.user_id in owners and
                 all(a.matched_workout_id == prescription.workout_id for a in ordered))
    if prescription is None:
        limitations.append('missing_prescription')
    elif prescription.confidence != 'known':
        limitations.append('uncertain_prescription')
    elif not known:
        limitations.append('unconfirmed_workout_pairing')
    if known and prescription.revision_id is None:
        limitations.append('prescription_revision_missing')
    planned = _expand(prescription.workout.steps) if prescription else ()
    if known and prescription.workout.planned_duration_minutes is not None:
        expected = prescription.workout.planned_duration_minutes * 60
        fact('planned_duration_seconds', expected, evidence=(prescription.revision_id or prescription.workout_id,))
        fact('duration_delta_seconds', actual - expected,
             evidence=refs + (prescription.revision_id or prescription.workout_id,))
    if known and prescription.workout.planned_distance_meters is not None:
        planned_distance = prescription.workout.planned_distance_meters
        fact('planned_distance_meters', planned_distance, 'm',
             evidence=(prescription.revision_id or prescription.workout_id,))
        fact('distance_delta_meters', actual_distance - planned_distance, 'm',
             evidence=refs + (prescription.revision_id or prescription.workout_id,))

    exact = known and prescription.revision_id is not None and bool(planned) and len(ordered) == 1 and bool(segments)
    mapped: dict[str, tuple[DetailSnapshot, ActivitySegment]] = {}
    if exact:
        by_key = {(step.fit_index, step.occurrence): step for step in planned}
        positions = {step.scope: i for i, step in enumerate(planned)}
        previous_end, previous_position = None, -1
        for source, segment in segments:
            path = segment.step_path or ''
            index = path.removeprefix('fit_step/') if path.startswith('fit_step/') else ''
            key = (int(index), segment.metadata.get('repeat_occurrence')) if index.isdigit() else None
            step = by_key.get(key)
            start = _utc(segment.start_at) if segment.start_at else None
            end = _utc(segment.end_at) if segment.end_at else None
            historical_bound = (step is not None and (
                step.step.duration_seconds is not None and
                segment.metadata.get('fit_planned_duration_seconds') is not None and
                abs(segment.metadata['fit_planned_duration_seconds'] - step.step.duration_seconds) <= 5
                or step.step.duration_seconds is None and step.step.distance_meters is not None and
                segment.metadata.get('fit_planned_distance_meters') is not None and
                abs(segment.metadata['fit_planned_distance_meters'] - step.step.distance_meters) <= 5))
            if not (step and source.resource == 'fit' and segment.source_kind == 'fit_lap' and
                    historical_bound and
                    segment.metadata.get('lap_trigger') in ('manual', 'time') and
                    segment.timer_seconds is not None and segment.timer_seconds > 0 and
                    start and end and end >= start and
                    (previous_end is None or start >= previous_end) and
                    positions[step.scope] > previous_position):
                exact = False
                break
            mapped[step.scope] = (source, segment)
            previous_end, previous_position = end, positions[step.scope]
    if not exact:
        mapped.clear()
    mapping = 'exact' if exact else 'unmatched'
    if not exact and known and planned and len(ordered) == 1 and len(segments) == len(planned):
        # A unique ordered boundary can be estimated, but does not identify a measured Workout Step.
        signatures = [(step.step.duration_seconds, step.step.distance_meters) for step in planned]
        if (len(set(signatures)) == len(signatures) and
                all(segment.start_at and segment.end_at and (
                step.step.duration_seconds is not None and segment.timer_seconds is not None and
                abs(segment.timer_seconds - step.step.duration_seconds) <= 5
                or step.step.distance_meters is not None and segment.distance_meters is not None and
                abs(segment.distance_meters - step.step.distance_meters) <= 5)
                for (_, segment), step in zip(segments, planned)) and
                all(_utc(left.end_at) <= _utc(right.start_at)
                    for (_, left), (_, right) in zip(segments, segments[1:]))):
            mapping = 'estimated'
            limitations.append('ordered_boundary_estimate_not_step_identity')
    if mapping != 'exact' and segments:
        limitations.append('step_mapping_unverified')

    for step in planned:
        if step.scope not in mapped:
            continue
        source, segment = mapped[step.scope]
        measured = fact('step_timer_seconds', segment.timer_seconds, scope=step.scope,
                        evidence=(source.id, prescription.revision_id or prescription.workout_id))
        if segment.distance_meters is not None and step.step.distance_meters is not None:
            fact('step_distance_delta_meters', segment.distance_meters - step.step.distance_meters,
                 'm', step.scope, (source.id, prescription.revision_id or prescription.workout_id))
        if step.step.duration_seconds is not None and segment.timer_seconds > step.step.duration_seconds:
            if step.step.step_type in ('work', 'cooldown'):
                code = f'{step.step.step_type}_volume_over'
                delta_fact = fact('step_duration_delta_seconds',
                    segment.timer_seconds - step.step.duration_seconds, scope=step.scope,
                    evidence=(source.id, prescription.revision_id or prescription.workout_id))
                finding(code, (measured, delta_fact),
                        'recorded timer duration exceeded this Workout Step',
                        'physiological cause, injury risk or intent')
    if exact and any(step.occurrence > 1 and step.scope not in mapped for step in planned):
        missing = fact('missing_repeat_steps', sum(step.scope not in mapped for step in planned),
                       'steps', evidence=(prescription.revision_id or prescription.workout_id,))
        finding('missed_repeat', missing, 'fewer repeat steps were recorded than planned',
                'why the repeat was not recorded')
    seen_linked = False
    unlinked_tail_seconds = 0.0
    for _, segment in segments:
        if segment.step_path is not None:
            seen_linked = True
        elif seen_linked:
            unlinked_tail_seconds += segment.timer_seconds or 0
    if segments and (recorded + 5 < summary or unlinked_tail_seconds > 0):
        tail = fact('unmatched_timer_seconds', max(0, summary - recorded) + unlinked_tail_seconds,
                    evidence=refs)
        finding('unmatched_tail', tail, 'recorded time lacks verified Workout Step assignment',
                'which Workout Step received the time')
    paces = [segment.average_pace_seconds_per_km for _, segment in segments
             if segment.average_pace_seconds_per_km is not None]
    if len(paces) > 1:
        fact('lap_pace_range_seconds_per_km', max(paces) - min(paces), 's/km')
    if any(step.step.target and not (step.step.target.pace_range_seconds_per_km or
                                     step.step.target.heart_rate_range_bpm) for step in planned):
        limitations.append('historical_target_range_missing')
    _target_time(ordered, snapshots, planned, mapped, fact, limitations)
    return ExecutionAnalysis(ordered[0].id, tuple(a.id for a in ordered),
        _fingerprint(prescription, ordered, snapshots),
        prescription.revision_id if prescription else None, refs, mapping,
        tuple(facts), tuple(findings), tuple(dict.fromkeys(limitations)))


def _target_time(activities, snapshots, planned, mapped, fact, limitations):
    if len(activities) != 1 or not mapped:
        return
    source = next((s for s in snapshots if s.activity_id == activities[0].id and
                   s.resource == 'fit' and s.details.coverage.state == 'complete' and
                   s.details.coverage.sampling == 'recorded' and s.sample_chunks), None)
    if source is None:
        return
    samples = sorted((row for chunk in source.sample_chunks for row in chunk.samples),
                     key=lambda row: row.get('at', ''))
    for step in planned:
        if step.scope not in mapped or step.step.target is None:
            continue
        target = step.step.target
        bounds = target.pace_range_seconds_per_km or target.heart_rate_range_bpm
        metric = 'pace_seconds_per_km' if target.pace_range_seconds_per_km else 'heart_rate_bpm'
        if bounds is None:
            continue
        segment = mapped[step.scope][1]
        if segment.start_at is None or segment.end_at is None:
            continue
        covered = in_range = 0.0
        for left, right in zip(samples, samples[1:]):
            try:
                start = _utc(datetime.fromisoformat(left['at']))
                end = _utc(datetime.fromisoformat(right['at']))
            except (KeyError, TypeError, ValueError):
                continue
            duration = (end - start).total_seconds()
            value = right.get(metric)
            if (not 0 < duration <= 30 or start < _utc(segment.start_at) or
                    end > _utc(segment.end_at) or left.get('timer_running') is not True or
                    right.get('timer_running') is not True or
                    not isinstance(value, (int, float)) or isinstance(value, bool)):
                continue
            covered += duration
            if bounds[0] <= value <= bounds[1]:
                in_range += duration
        if covered:
            fact('target_time_seconds', in_range, scope=step.scope, evidence=(source.id,),
                 denominator=segment.timer_seconds, covered=covered)
            if covered < segment.timer_seconds:
                limitations.append('target_interval_coverage_partial')
