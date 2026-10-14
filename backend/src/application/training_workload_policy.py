"""Versioned, deterministic running workload inputs and policy."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from statistics import median
from typing import Any, Mapping, Sequence
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


from src.domain.running import RUNNING_SPORTS
POLICY_VERSION = "race-workload-v2"


@dataclass(frozen=True)
class CapacitySnapshot:
    source: str
    confidence: str
    weekly_minutes: int | None
    weekly_distance_km: float | None
    recent_long_run_minutes: int | None
    observation_start: date
    observation_end: date
    activity_count: int
    missing_dimensions: tuple[str, ...]
    recent_ascent_meters: float | None = None


@dataclass(frozen=True)
class RaceDemand:
    distance_meters: float
    race_date: date
    target_finish_seconds: int | None
    ascent_meters: float | None
    descent_meters: float | None
    terrain_difficulty: str | None
    cutoff_seconds: int | None
    goal_intent: str | None


@dataclass(frozen=True)
class WorkloadWeek:
    week_index: int
    target_minutes: int
    long_run_minutes: int
    phase: str
    terrain_focus: bool


@dataclass(frozen=True)
class PreparationAssessment:
    status: str
    factors: tuple[str, ...]
    explanation_zh: str
    policy_version: str


@dataclass(frozen=True)
class WorkloadPrescription:
    weeks: tuple[WorkloadWeek, ...]
    assessment: PreparationAssessment
    policy_version: str


def derive_capacity_snapshot(*, profile: dict, activities: Sequence[dict], anchor: date) -> CapacitySnapshot:
    """Estimate weekly capacity from four complete athlete-local calendar weeks."""
    completed_end = anchor - timedelta(days=anchor.weekday() + 1)
    completed_start = completed_end - timedelta(days=27)
    try:
        athlete_zone = ZoneInfo(str(profile.get("timezone") or "UTC"))
    except ZoneInfoNotFoundError:
        athlete_zone = ZoneInfo("UTC")
    seen: set[tuple[str, str]] = set()
    valid: list[tuple[date, float, float]] = []
    ascent_observations: list[tuple[date, float]] = []
    for item in activities:
        if str(item.get("sport_type") or "").lower() not in RUNNING_SPORTS:
            continue
        identity = (("id", str(item["id"])) if item.get("id") else (str(item.get("source") or ""), str(item.get("source_activity_id") or "")))
        if not identity[1] or identity in seen:
            continue
        try:
            started = datetime.fromisoformat(str(item["started_at"]).replace("Z", "+00:00"))
            local_day = (started.astimezone(athlete_zone) if started.tzinfo else started).date()
            seconds = float(item.get("duration_seconds") or 0)
            meters = float(item.get("distance_meters") or 0)
        except (KeyError, TypeError, ValueError, OverflowError):
            continue
        if seconds <= 0 or meters < 0 or local_day >= anchor or local_day < anchor - timedelta(days=56):
            continue
        seen.add(identity)
        valid.append((local_day, seconds / 60, meters / 1000))
        if item.get("elevation_gain_meters") is not None:
            try:
                ascent = float(item["elevation_gain_meters"])
            except (TypeError, ValueError):
                ascent = -1
            if ascent >= 0:
                ascent_observations.append((local_day, ascent))

    weeks = [[entry for entry in valid if completed_start + timedelta(days=7 * index) <= entry[0] < completed_start + timedelta(days=7 * (index + 1))] for index in range(4)]
    complete_runs = [entry for week in weeks for entry in week]
    sufficient = (len(complete_runs) >= 8 and sum(len(week) >= 2 for week in weeks) >= 3 and any(day >= anchor - timedelta(days=14) for day, _, _ in valid))
    recent_long = max((minutes for day, minutes, _ in valid if day >= anchor - timedelta(days=28)), default=None)
    recent_ascent = sum(ascent for day, ascent in ascent_observations if day >= anchor - timedelta(days=28)) if ascent_observations else None
    if sufficient:
        return CapacitySnapshot(
            source="activities", confidence="high",
            weekly_minutes=round(median(sum(minutes for _, minutes, _ in week) for week in weeks)),
            weekly_distance_km=round(float(median(sum(km for _, _, km in week) for week in weeks)), 2),
            recent_long_run_minutes=round(recent_long) if recent_long is not None else None,
            observation_start=completed_start, observation_end=completed_end,
            activity_count=len(complete_runs), missing_dimensions=(),
            recent_ascent_meters=recent_ascent,
        )
    try:
        stated_km = float(profile.get("current_weekly_mileage_km") or 0)
    except (TypeError, ValueError):
        stated_km = 0
    return CapacitySnapshot(
        source="stated_mileage" if stated_km > 0 else "missing", confidence="low",
        weekly_minutes=round(stated_km * 6) if stated_km > 0 else None,
        weekly_distance_km=stated_km if stated_km > 0 else None,
        recent_long_run_minutes=round(recent_long) if recent_long is not None else None,
        observation_start=completed_start, observation_end=completed_end,
        activity_count=len(complete_runs),
        missing_dimensions=("activity_history",) if stated_km > 0 else ("activity_history", "weekly_mileage"),
        recent_ascent_meters=recent_ascent,
    )


def _phase_for(day: date, segments: Sequence[dict]) -> str:
    return next((str(segment["phase"]) for segment in segments if date.fromisoformat(segment["starts_on"]) <= day <= date.fromisoformat(segment["ends_on"])), "base")


def build_workload_prescription(
    *, capacity: CapacitySnapshot, race: RaceDemand | None, starts_on: date, ends_on: date,
    phase_segments: Sequence[dict], max_runs_per_week: int, max_hard_sessions_per_week: int,
    injury_status: str, prior_plan: Mapping[str, Any] | None = None,
) -> WorkloadPrescription:
    if ends_on < starts_on or max_runs_per_week < 1:
        raise ValueError("invalid training window or run limit")
    injured = injury_status in {"current", "recent"}
    baseline = capacity.weekly_minutes
    missing_baseline = baseline is None
    if missing_baseline:
        baseline = max_runs_per_week * 20 + 10  # 20-minute ordinary runs and a 30-minute long run
    baseline = round(baseline * .8) if injured else baseline
    prior_longs: list[int] = []
    if isinstance(prior_plan, Mapping):
        for workout in prior_plan.get("workouts", ()):
            if not isinstance(workout, Mapping) or workout.get("workout_type") != "long_run" or workout.get("status") == "skipped":
                continue
            try:
                scheduled_for = date.fromisoformat(str(workout["scheduled_for"]))
                minutes = int(workout["planned_duration_minutes"])
            except (KeyError, TypeError, ValueError):
                continue
            if starts_on - timedelta(days=28) <= scheduled_for < starts_on and minutes > 0:
                prior_longs.append(minutes)
    long_anchor = max(capacity.recent_long_run_minutes or 0, max(prior_longs, default=0)) or (30 if missing_baseline else min(90, round(.4 * baseline)))
    long_cap = 180 if race is not None and 30_000 <= race.distance_meters <= 50_000 else 90 if race is not None and race.distance_meters <= 10_000 else 120
    week_starts = []
    current = starts_on
    while current <= ends_on:
        week_starts.append(current)
        current += timedelta(days=7)
    development_indexes = [index for index, day in enumerate(week_starts) if _phase_for(day, phase_segments) not in {"taper", "race"}]
    terrain_indexes: set[int] = set()
    if race is not None and race.terrain_difficulty in {"mixed", "technical"} and max_hard_sessions_per_week >= 2 and not injured:
        candidates = development_indexes[-8:]
        terrain_indexes = set(candidates[-2:])
    weeks: list[WorkloadWeek] = []
    development_high = baseline
    previous_target = baseline
    development_number = 0
    for index, day in enumerate(week_starts):
        phase = _phase_for(day, phase_segments)
        if phase == "taper":
            target = round(previous_target * .65)
        elif phase == "race":
            target = min(previous_target, baseline)
        else:
            development_number += 1
            if injured or missing_baseline:
                target = baseline
            elif development_number == 1:
                target = baseline
            elif development_number % 4 == 0:
                target = round(previous_target * .85)
            else:
                development_high = round(development_high * 1.05)
                target = development_high
        # The final partial week cannot carry the volume of a full calendar week.
        available_days = min(7, (ends_on - day).days + 1)
        if available_days < 7:
            target = round(target * available_days / 7)
        long_minutes = min(30 if missing_baseline else round(long_anchor * 1.1), round(target * .5), long_cap)
        if phase == "race":
            long_minutes = min(long_minutes, 30)
        weeks.append(WorkloadWeek(index, target, long_minutes, phase, index in terrain_indexes))
        previous_target = target
        long_anchor = long_minutes
    assessment = assess_preparation(
        capacity=capacity, race=race, starts_on=starts_on, ends_on=ends_on,
        weekly_minutes=[week.target_minutes for week in weeks if week.phase not in {"taper", "race"}],
        long_run_minutes=[week.long_run_minutes for week in weeks if week.phase not in {"taper", "race"}],
        terrain_session_count=len(terrain_indexes), policy_version=POLICY_VERSION,
    )
    return WorkloadPrescription(tuple(weeks), assessment, POLICY_VERSION)


def assess_preparation(
    *, capacity: CapacitySnapshot, race: RaceDemand | None, starts_on: date, ends_on: date,
    weekly_minutes: Sequence[int], long_run_minutes: Sequence[int], terrain_session_count: int,
    policy_version: str,
) -> PreparationAssessment:
    factors: list[str] = []
    unknown: list[str] = []
    calibrated = race is not None and 30_000 <= race.distance_meters <= 50_000 and race.race_date <= ends_on + timedelta(days=1)
    if capacity.confidence != "high":
        unknown.append("missing_baseline")
    if race is None or not calibrated:
        unknown.append("uncalibrated_race")
    if calibrated:
        if max(weekly_minutes, default=0) < 300:
            factors.append("weekly_volume")
        if max(long_run_minutes, default=0) < 150:
            factors.append("long_run_endurance")
        if race.terrain_difficulty in {"mixed", "technical"} and terrain_session_count < 2:
            factors.append("terrain_exposure")
        if race.ascent_meters is not None:
            if terrain_session_count == 0:
                factors.append("ascent_preparation")
            # V1 has no calibrated ascent target or downhill evidence. A hill
            # session alone must not turn known climbing demands into on_track.
            unknown.append("uncalibrated_ascent")
        if (ends_on - starts_on).days < 55:
            factors.append("short_horizon")
    status = "gap" if factors else "unknown" if unknown else "on_track"
    labels = {
        "weekly_volume": "每週跑量低於此距離的規劃參考值",
        "long_run_endurance": "最長跑步時間低於此距離的規劃參考值",
        "terrain_exposure": "缺少足夠的地形專項訓練",
        "ascent_preparation": "缺少爬升專項訓練",
        "short_horizon": "準備時間較短",
        "missing_baseline": "近期跑步紀錄不足",
        "uncalibrated_race": "此賽事距離尚無完整評估參考值",
        "uncalibrated_ascent": "爬升需求尚無完整評估參考值",
    }
    explanation = "；".join(labels[factor] for factor in (*factors, *unknown)) if factors or unknown else "規劃訓練達到目前政策參考值；不代表保證完賽。"
    return PreparationAssessment(status, tuple((*factors, *unknown)), explanation, policy_version)
