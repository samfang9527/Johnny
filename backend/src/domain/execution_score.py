"""Versioned, deterministic adherence scoring for seven completed local days."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

from src.domain.running import RUNNING_WORKOUT_TYPES
from src.domain.training_review import ReviewEvidence


POLICY_VERSION = "execution-v1"


@dataclass(frozen=True)
class ExecutionScore:
    value: int | None
    completion_component: float | None
    volume_component: float | None
    eligible_count: int
    completed_count: int
    missed_count: int
    extra_count: int
    covered_date_count: int
    reason: str | None
    policy_version: str = POLICY_VERSION


def score_execution(evidence: ReviewEvidence) -> ExecutionScore:
    eligible = tuple(
        snapshot for snapshot in evidence.prescriptions
        if snapshot.workout.workout_type in RUNNING_WORKOUT_TYPES
        and not (snapshot.workout.status == "skipped" and snapshot.source == "approved_adjustment")
    )
    matched: dict[str, list] = {}
    ambiguous_dates = set()
    extra_count = 0
    for session in evidence.sessions:
        if session.status == "needs_review":
            ambiguous_dates.add(session.local_date)
        elif session.workout_id is not None:
            matched.setdefault(session.workout_id, []).append(session)
        elif session.status == "unplanned":
            extra_count += 1
    completed = sum(bool(matched.get(snapshot.workout_id)) for snapshot in eligible)
    missed = sum(
        snapshot.confidence == "known"
        and snapshot.workout.scheduled_for in evidence.covered_dates
        and snapshot.workout.scheduled_for not in ambiguous_dates
        and not matched.get(snapshot.workout_id)
        for snapshot in eligible
    )
    common = dict(
        eligible_count=len(eligible), completed_count=completed, missed_count=missed,
        extra_count=extra_count, covered_date_count=len(evidence.covered_dates),
    )
    def withheld(reason: str) -> ExecutionScore:
        return ExecutionScore(None, None, None, reason=reason, **common)

    if not eligible:
        return withheld("no_prescribed_sessions")
    if any(snapshot.confidence != "known" for snapshot in eligible):
        return withheld("uncertain_prescription")
    if evidence.uncertainty_reasons:
        return withheld(evidence.uncertainty_reasons[0])
    if any(snapshot.workout.scheduled_for in ambiguous_dates for snapshot in eligible):
        return withheld("ambiguous_pairing")
    if any(snapshot.workout.scheduled_for not in evidence.covered_dates for snapshot in eligible):
        return withheld("incomplete_activity_coverage")

    completion_sum = Decimal(0)
    volume_sum = Decimal(0)
    for snapshot in eligible:
        workout = snapshot.workout
        sessions = matched.get(snapshot.workout_id, [])
        if workout.workout_type == "race":
            planned = workout.planned_distance_meters
            actual = sum((session.distance_meters for session in sessions), 0.0)
        elif workout.planned_duration_minutes is not None:
            planned = workout.planned_duration_minutes * 60
            actual = sum((session.duration_seconds for session in sessions), 0)
        else:
            planned = workout.planned_distance_meters
            actual = sum((session.distance_meters for session in sessions), 0.0)
        if planned is None or planned <= 0 or any(
            activity.distance_meters <= 0 for session in sessions for activity in session.activities
        ) and (workout.workout_type == "race" or workout.planned_duration_minutes is None):
            return withheld("missing_comparison_metric")
        if sessions:
            completion_sum += 1
        if actual > 0:
            ratio = Decimal(str(actual)) / Decimal(str(planned))
            volume_sum += min(ratio, 1 / ratio)
    denominator = Decimal(len(eligible))
    completion = Decimal(100) * completion_sum / denominator
    volume = Decimal(100) * volume_sum / denominator
    value = int(((completion + volume) / 2).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    return ExecutionScore(value, float(completion), float(volume), reason=None, **common)
