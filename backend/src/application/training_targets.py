from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.domain.activity_health import CompletedActivity
from src.domain.athlete_race import AthleteProfile, RaceGoal
from src.domain.training_plan import WorkoutStep, WorkoutTarget


PACE_ZONE_FACTORS = {
    "easy": (1.20, 1.35),
    "steady": (1.10, 1.18),
    "marathon": (1.06, 1.12),
    "threshold": (0.9833333333333333, 1.0166666666666666),
    "interval": (0.92, 0.97),
    "repetition": (0.85, 0.90),
}
ZONE_RPE = {
    "easy": 3,
    "steady": 5,
    "marathon": 6,
    "threshold": 7,
    "interval": 8,
    "repetition": 9,
    "rpe_only": 5,
}


@dataclass(frozen=True)
class PaceProfile:
    source: str
    confidence: str
    zones: dict[str, tuple[int, int]]

    def to_payload(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "confidence": self.confidence,
            "zones": {zone: list(pace_range) for zone, pace_range in self.zones.items()},
        }

    @classmethod
    def from_payload(cls, payload: dict[str, Any] | None) -> PaceProfile | None:
        if not payload:
            return None
        return cls(
            source=str(payload.get("source") or "unknown"),
            confidence=str(payload.get("confidence") or "low"),
            zones={
                str(zone): (int(pace_range[0]), int(pace_range[1]))
                for zone, pace_range in dict(payload.get("zones") or {}).items()
                if isinstance(pace_range, list | tuple) and len(pace_range) == 2
            },
        )


def build_pace_profile(
    *,
    profile: AthleteProfile | None,
    selected_race: RaceGoal | None = None,
    recent_activities: tuple[CompletedActivity, ...] = (),
) -> PaceProfile:
    threshold_pace = _threshold_pace_seconds_per_km(profile)
    if threshold_pace is not None:
        return _profile_from_baseline(source="threshold_pace", confidence="high", pace_seconds_per_km=threshold_pace)

    if selected_race is not None and selected_race.target_pace_seconds_per_km is not None:
        return _profile_from_baseline(
            source="race_target",
            confidence="low",
            pace_seconds_per_km=selected_race.target_pace_seconds_per_km,
        )

    activity = next((item for item in recent_activities if item.average_pace_seconds_per_km > 0), None)
    if activity is not None:
        return _profile_from_baseline(
            source="recent_activity",
            confidence="low",
            pace_seconds_per_km=activity.average_pace_seconds_per_km,
        )

    return PaceProfile(source="missing_baseline", confidence="low", zones={})


def build_pace_profile_from_payloads(
    *,
    profile_payload: dict[str, Any] | None,
    selected_race_payload: dict[str, Any] | None = None,
    recent_activity_payloads: tuple[dict[str, Any], ...] = (),
) -> PaceProfile:
    threshold_pace = _threshold_pace_from_payload(profile_payload)
    if threshold_pace is not None:
        return _profile_from_baseline(source="threshold_pace", confidence="high", pace_seconds_per_km=threshold_pace)

    if selected_race_payload is not None and selected_race_payload.get("target_pace_seconds_per_km") is not None:
        return _profile_from_baseline(
            source="race_target",
            confidence="low",
            pace_seconds_per_km=float(selected_race_payload["target_pace_seconds_per_km"]),
        )

    activity = next((item for item in recent_activity_payloads if float(item.get("average_pace_seconds_per_km") or 0) > 0), None)
    if activity is not None:
        return _profile_from_baseline(
            source="recent_activity",
            confidence="low",
            pace_seconds_per_km=float(activity["average_pace_seconds_per_km"]),
        )

    return PaceProfile(source="missing_baseline", confidence="low", zones={})


def enrich_workout_steps(
    steps: tuple[WorkoutStep, ...],
    *,
    pace_profile: PaceProfile | None,
) -> tuple[WorkoutStep, ...]:
    return tuple(_enrich_step(step, pace_profile=pace_profile) for step in steps)


def _enrich_step(step: WorkoutStep, *, pace_profile: PaceProfile | None) -> WorkoutStep:
    if step.step_type == "repeat":
        return WorkoutStep.create(
            step_type=step.step_type,
            duration_seconds=step.duration_seconds,
            distance_meters=step.distance_meters,
            target=step.target,
            repeat_count=step.repeat_count,
            steps=enrich_workout_steps(step.steps, pace_profile=pace_profile),
            notes=step.notes,
            grade_notes=step.grade_notes,
        )
    target = _enrich_target(step.target, pace_profile=pace_profile)
    return WorkoutStep.create(
        step_type=step.step_type,
        duration_seconds=step.duration_seconds,
        distance_meters=step.distance_meters,
        target=target,
        notes=step.notes,
        grade_notes=step.grade_notes,
    )


def _enrich_target(target: WorkoutTarget | None, *, pace_profile: PaceProfile | None) -> WorkoutTarget | None:
    if target is None or target.kind != "pace" or target.zone is None:
        return target
    rpe = target.rpe or ZONE_RPE[target.zone]
    if pace_profile is None or pace_profile.confidence == "low" or target.zone == "rpe_only":
        return WorkoutTarget.rpe(rpe)
    pace_range = pace_profile.zones.get(target.zone)
    if pace_range is None:
        return WorkoutTarget.rpe(rpe)
    return WorkoutTarget.pace(
        zone=target.zone,
        pace_range_seconds_per_km=pace_range,
        rpe=rpe,
        confidence=pace_profile.confidence,
    )


def _profile_from_baseline(*, source: str, confidence: str, pace_seconds_per_km: float) -> PaceProfile:
    zones = {
        zone: (
            max(1, round(pace_seconds_per_km * lower)),
            max(1, round(pace_seconds_per_km * upper)),
        )
        for zone, (lower, upper) in PACE_ZONE_FACTORS.items()
    }
    return PaceProfile(source=source, confidence=confidence, zones=zones)


def _threshold_pace_seconds_per_km(profile: AthleteProfile | None) -> float | None:
    if profile is None:
        return None
    value = profile.preferences.training_preferences.get("threshold_pace_seconds_per_km")
    if value is None:
        value = profile.preferences.training_preferences.get("threshold_pace_sec_per_km")
    if value is None:
        return None
    pace = float(value)
    return pace if pace > 0 else None


def _threshold_pace_from_payload(profile_payload: dict[str, Any] | None) -> float | None:
    if not profile_payload:
        return None
    preferences = dict(profile_payload.get("training_preferences") or {})
    value = preferences.get("threshold_pace_seconds_per_km")
    if value is None:
        value = preferences.get("threshold_pace_sec_per_km")
    if value is None:
        return None
    pace = float(value)
    return pace if pace > 0 else None
