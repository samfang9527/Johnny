"""Versioned, deterministic running workload inputs and policy."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from statistics import median
from typing import Any, Sequence
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


RUNNING_SPORTS = frozenset({"run", "running", "trail_run", "trail_running", "virtual_run", "treadmill_run"})


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
    for item in activities:
        if str(item.get("sport_type") or "").lower() not in RUNNING_SPORTS:
            continue
        identity = (("id", str(item["id"])) if item.get("id") else (str(item.get("source") or ""), str(item.get("source_activity_id") or "")))
        if not identity[1] or identity in seen:
            continue
        seen.add(identity)
        try:
            started = datetime.fromisoformat(str(item["started_at"]).replace("Z", "+00:00"))
            local_day = (started.astimezone(athlete_zone) if started.tzinfo else started).date()
            seconds = float(item.get("duration_seconds") or 0)
            meters = float(item.get("distance_meters") or 0)
        except (KeyError, TypeError, ValueError, OverflowError):
            continue
        if seconds <= 0 or meters < 0 or local_day >= anchor or local_day < anchor - timedelta(days=56):
            continue
        valid.append((local_day, seconds / 60, meters / 1000))

    weeks = [[entry for entry in valid if completed_start + timedelta(days=7 * index) <= entry[0] < completed_start + timedelta(days=7 * (index + 1))] for index in range(4)]
    complete_runs = [entry for week in weeks for entry in week]
    sufficient = (len(complete_runs) >= 8 and sum(len(week) >= 2 for week in weeks) >= 3 and any(day >= anchor - timedelta(days=14) for day, _, _ in valid))
    recent_long = max((minutes for day, minutes, _ in valid if day >= anchor - timedelta(days=28)), default=None)
    if sufficient:
        return CapacitySnapshot(
            source="activities", confidence="high",
            weekly_minutes=round(median(sum(minutes for _, minutes, _ in week) for week in weeks)),
            weekly_distance_km=round(float(median(sum(km for _, _, km in week) for week in weeks)), 2),
            recent_long_run_minutes=round(recent_long) if recent_long is not None else None,
            observation_start=completed_start, observation_end=completed_end,
            activity_count=len(complete_runs), missing_dimensions=(),
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
    )
