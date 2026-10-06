from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from statistics import median
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
TARGET_POLICY_VERSION = "target-evidence-v1"
HR_RESERVE_BANDS = {
    "recovery": (.40, .55),
    "easy": (.50, .65),
    "steady": (.65, .75),
    "marathon": (.70, .80),
    "threshold": (.80, .90),
}
RPE_ZONE = {
    1: "easy", 2: "easy", 3: "easy", 4: "easy", 5: "steady",
    6: "marathon", 7: "threshold", 8: "interval", 9: "repetition", 10: "repetition",
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


@dataclass(frozen=True)
class TargetProfile:
    resting_heart_rate_bpm: int | None
    max_heart_rate_bpm: int | None
    heart_rate_zones: dict[str, tuple[int, int]]
    pace_source: str | None
    pace_confidence: str | None
    pace_zones: dict[str, tuple[int, int]]
    policy_version: str = TARGET_POLICY_VERSION

    def to_payload(self) -> dict[str, Any]:
        return {
            "resting_heart_rate_bpm": self.resting_heart_rate_bpm,
            "max_heart_rate_bpm": self.max_heart_rate_bpm,
            "heart_rate_zones": {key: list(value) for key, value in self.heart_rate_zones.items()},
            "pace_source": self.pace_source,
            "pace_confidence": self.pace_confidence,
            "pace_zones": {key: list(value) for key, value in self.pace_zones.items()},
            "policy_version": self.policy_version,
        }

    @classmethod
    def from_payload(cls, payload: dict[str, Any] | None) -> TargetProfile:
        if not isinstance(payload, dict):
            return cls(None, None, {}, None, None, {})
        if "pace_zones" not in payload and "zones" in payload:
            # Already queued legacy runs carried only a pace profile. Preserve
            # measured threshold evidence but discard ambiguous old anchors.
            source = payload.get("source")
            zones = payload.get("zones") if source == "threshold_pace" else {}
            return cls(None, None, {}, source if zones else None, "high" if zones else None, _valid_zone_ranges(zones))
        resting = _positive_int(payload.get("resting_heart_rate_bpm"))
        maximum = _positive_int(payload.get("max_heart_rate_bpm"))
        if resting is None or maximum is None or maximum <= resting:
            resting, maximum = None, None
        return cls(
            resting, maximum,
            _heart_rate_zones(resting, maximum) if resting is not None and maximum is not None else {},
            str(payload["pace_source"]) if payload.get("pace_source") in {"threshold_pace", "completed_race", "paired_easy_activities", "goal_time"} else None,
            str(payload["pace_confidence"]) if payload.get("pace_confidence") in {"high", "medium", "low"} else None,
            _valid_zone_ranges(payload.get("pace_zones")),
        )


def build_target_profile_from_payloads(
    profile_payload: dict[str, Any] | None,
    selected_race_payload: dict[str, Any] | None,
    recent_activity_payloads: tuple[dict, ...],
    prior_plan_payload: dict[str, Any] | None,
) -> TargetProfile:
    profile = profile_payload if isinstance(profile_payload, dict) else {}
    preferences = profile.get("training_preferences") if isinstance(profile.get("training_preferences"), dict) else {}
    resting = _positive_int(profile.get("resting_heart_rate_bpm", preferences.get("resting_heart_rate_bpm")))
    maximum = _positive_int(profile.get("max_heart_rate_bpm", preferences.get("max_heart_rate_bpm")))
    if resting is None or maximum is None or maximum <= resting:
        resting, maximum = None, None
    heart_rate_zones = _heart_rate_zones(resting, maximum) if resting is not None and maximum is not None else {}
    anchor = _anchor_date(profile, recent_activity_payloads)
    source: str | None = None
    confidence: str | None = None
    zones: dict[str, tuple[int, int]] = {}

    threshold = _positive_int(preferences.get("threshold_pace_seconds_per_km"))
    if threshold is not None and 120 <= threshold <= 900:
        source, confidence = "threshold_pace", "high"
        zones = _zones_from_reference(threshold, "threshold", widening=0)
    else:
        matched_workouts = {
            str(item["id"]): item
            for item in (prior_plan_payload or {}).get("workouts", ())
            if isinstance(item, dict) and item.get("id")
        }
        completed_races: list[tuple[date, float, int]] = []
        paired_easy: list[float] = []
        for activity in recent_activity_payloads:
            if not isinstance(activity, dict) or str(activity.get("sport_type") or "").lower() not in {"run", "running", "trail_run", "trail_running", "virtual_run", "treadmill_run"}:
                continue
            day = _activity_date(activity)
            if day is None or anchor is None or day > anchor or day < anchor - timedelta(days=56):
                continue
            matched = matched_workouts.get(str(activity.get("matched_workout_id") or ""))
            meters = _positive_number(activity.get("distance_meters"))
            seconds = _positive_number(activity.get("duration_seconds"))
            if matched is None or meters is None or seconds is None:
                continue
            pace = seconds / (meters / 1000)
            if not 120 <= pace <= 1200:
                continue
            if matched.get("workout_type") == "race" and matched.get("status") == "completed":
                race_meters = _positive_number(matched.get("planned_distance_meters"))
                if race_meters is not None and abs(meters - race_meters) / race_meters <= .05:
                    completed_races.append((day, pace, round(race_meters)))
            if matched.get("workout_type") in {"easy_run", "long_run"} and day >= anchor - timedelta(days=28) and meters >= 3000 and seconds >= 1200 and heart_rate_zones:
                ascent = activity.get("elevation_gain_meters")
                heart_rate = _positive_number(activity.get("average_heart_rate"))
                if ascent is None or heart_rate is None:
                    continue
                try:
                    ascent_per_km = float(ascent) / (meters / 1000)
                except (TypeError, ValueError):
                    continue
                lower_hr, upper_hr = heart_rate_zones["easy"]
                if 0 <= ascent_per_km <= 10 and lower_hr <= heart_rate <= upper_hr:
                    paired_easy.append(pace)
        if completed_races:
            _, pace, distance = max(completed_races, key=lambda item: item[0])
            source, confidence = "completed_race", "medium"
            zones = _zones_from_reference(pace, _race_reference_zone(distance), widening=.10)
        elif len(paired_easy) >= 3:
            source, confidence = "paired_easy_activities", "low"
            zones = _zones_from_reference(float(median(paired_easy)), "easy", widening=.15)
        else:
            race = selected_race_payload if isinstance(selected_race_payload, dict) else {}
            distance = _positive_number(race.get("distance_meters"))
            finish = _positive_number(race.get("target_finish_seconds"))
            if distance is not None and finish is not None:
                pace = finish / (distance / 1000)
                if 120 <= pace <= 1200:
                    source, confidence = "goal_time", "low"
                    zones = _zones_from_reference(pace, _race_reference_zone(round(distance)), widening=.20)
    return TargetProfile(resting, maximum, heart_rate_zones, source, confidence, zones)


def _positive_int(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else None


def _positive_number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 and number < float("inf") else None


def _activity_date(activity: dict) -> date | None:
    try:
        return datetime.fromisoformat(str(activity["started_at"]).replace("Z", "+00:00")).date()
    except (KeyError, ValueError, TypeError):
        return None


def _anchor_date(profile: dict, activities: tuple[dict, ...]) -> date | None:
    raw = profile.get("_planning_anchor")
    if isinstance(raw, str):
        try:
            return date.fromisoformat(raw)
        except ValueError:
            pass
    dates = [_activity_date(activity) for activity in activities if isinstance(activity, dict)]
    return max((day for day in dates if day is not None), default=None)


def _heart_rate_zones(resting: int, maximum: int) -> dict[str, tuple[int, int]]:
    reserve = maximum - resting
    return {zone: (round(resting + lower * reserve), round(resting + upper * reserve)) for zone, (lower, upper) in HR_RESERVE_BANDS.items()}


def _race_reference_zone(distance_meters: int) -> str:
    if distance_meters <= 5000:
        return "interval"
    if distance_meters <= 21_097:
        return "threshold"
    if distance_meters <= 42_195:
        return "marathon"
    return "easy"


def _zones_from_reference(pace: float, reference_zone: str, *, widening: float) -> dict[str, tuple[int, int]]:
    reference_factors = PACE_ZONE_FACTORS[reference_zone]
    threshold_equivalent = pace / (sum(reference_factors) / 2)
    return {
        zone: (
            max(1, round(threshold_equivalent * lower * (1 - widening))),
            max(1, round(threshold_equivalent * upper * (1 + widening))),
        )
        for zone, (lower, upper) in PACE_ZONE_FACTORS.items()
    }


def _valid_zone_ranges(value: Any) -> dict[str, tuple[int, int]]:
    if not isinstance(value, dict):
        return {}
    ranges = {}
    for zone, pair in value.items():
        if zone not in PACE_ZONE_FACTORS or not isinstance(pair, list | tuple) or len(pair) != 2:
            continue
        lower, upper = pair
        if isinstance(lower, int) and isinstance(upper, int) and 0 < lower <= upper:
            ranges[zone] = (lower, upper)
    return ranges


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
    pace_profile: PaceProfile | None = None,
    workout_type: str | None = None,
    target_profile: TargetProfile | None = None,
    race_rpe: int | None = None,
) -> tuple[WorkoutStep, ...]:
    if target_profile is not None:
        return tuple(
            _enrich_step_with_target_policy(
                step, workout_type=workout_type or "easy_run", target_profile=target_profile, race_rpe=race_rpe,
            )
            for step in steps
        )
    return tuple(_enrich_step(step, pace_profile=pace_profile) for step in steps)


def _enrich_step_with_target_policy(
    step: WorkoutStep, *, workout_type: str, target_profile: TargetProfile, race_rpe: int | None,
) -> WorkoutStep:
    if step.step_type == "repeat":
        return WorkoutStep.create(
            step_type="repeat", repeat_count=step.repeat_count,
            steps=enrich_workout_steps(step.steps, workout_type=workout_type, target_profile=target_profile, race_rpe=race_rpe),
            notes=step.notes, grade_notes=step.grade_notes,
        )
    target = step.target
    if workout_type in {"rest", "strength", "cross_training"}:
        target = None
    else:
        zone = target.zone if target is not None and target.zone in PACE_ZONE_FACTORS else None
        rpe = race_rpe if workout_type == "race" and race_rpe is not None else target.rpe if target is not None and target.rpe is not None else ZONE_RPE.get(zone or "easy", 3)
        zone = RPE_ZONE[rpe] if workout_type == "race" and race_rpe is not None else zone or RPE_ZONE[rpe]
        pace = target_profile.pace_zones.get(zone)
        pace_source = target_profile.pace_source if pace is not None else None
        confidence = target_profile.pace_confidence if pace is not None else None
        sustained = workout_type not in {"race", "interval", "hill"} or step.step_type in {"warmup", "cooldown"}
        heart_rate = target_profile.heart_rate_zones.get(zone) if sustained else None
        if heart_rate is not None:
            target = WorkoutTarget(
                kind="heart_rate", zone=zone, heart_rate_zone=zone, heart_rate_range_bpm=heart_rate,
                rpe=rpe, pace_range_seconds_per_km=pace, pace_source=pace_source, confidence=confidence,
            )
        else:
            target = WorkoutTarget(
                kind="rpe", zone=zone, rpe=rpe,
                pace_range_seconds_per_km=pace, pace_source=pace_source, confidence=confidence,
            )
    return WorkoutStep.create(
        step_type=step.step_type, duration_seconds=step.duration_seconds, distance_meters=step.distance_meters,
        target=target, notes=step.notes, grade_notes=step.grade_notes,
    )


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
    if target is not None and target.kind == "heart_rate":
        if target.heart_rate_range_bpm is not None:
            return target
        return WorkoutTarget.rpe(target.rpe) if target.rpe is not None else target
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
