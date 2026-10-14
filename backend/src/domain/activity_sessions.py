"""Deterministic running sessions; explicit athlete decisions always take precedence."""
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta, timezone
from hashlib import sha256
from zoneinfo import ZoneInfo

from src.domain.activity_health import CompletedActivity
from src.domain.running import RUNNING_WORKOUT_TYPES, is_running
from src.domain.training_plan import Workout


def utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


@dataclass(frozen=True)
class ActivitySession:
    id: str
    local_date: date
    activities: tuple[CompletedActivity, ...]
    status: str
    workout_id: str | None = None
    candidates: tuple[Workout, ...] = ()

    @property
    def duration_seconds(self) -> int:
        return sum(a.duration_seconds for a in self.activities)

    @property
    def distance_meters(self) -> float:
        return sum(a.distance_meters for a in self.activities)


def match_sessions(activities: tuple[CompletedActivity, ...], workouts: tuple[Workout, ...], timezone_name: str) -> tuple[ActivitySession, ...]:
    zone = ZoneInfo(timezone_name)
    ordered = sorted((a for a in activities if is_running(a.sport_type)), key=lambda a: (utc(a.started_at), a.id or ''))
    groups: list[list[CompletedActivity]] = []
    saved: dict[tuple, list[CompletedActivity]] = {}
    for activity in ordered:
        day = utc(activity.started_at).astimezone(zone).date()
        if activity.match_reviewed or activity.matched_workout_id:
            key = (activity.user_id, day, activity.session_group_id or activity.matched_workout_id or activity.id)
            if key not in saved:
                saved[key] = []
                groups.append(saved[key])
            saved[key].append(activity)
            continue
        previous = groups[-1][-1] if groups else None
        gap = utc(activity.started_at) - (utc(previous.started_at) + timedelta(seconds=previous.duration_seconds)) if previous else None
        if (previous and not previous.match_reviewed and not previous.matched_workout_id
                and previous.user_id == activity.user_id
                and utc(previous.started_at).astimezone(zone).date() == day
                and timedelta(0) <= gap <= timedelta(minutes=30)):
            groups[-1].append(activity)
        else:
            groups.append([activity])
    sessions = []
    for group in groups:
        first = group[0]
        day = utc(first.started_at).astimezone(zone).date()
        candidates = tuple(w for w in workouts if w.scheduled_for == day and w.workout_type in RUNNING_WORKOUT_TYPES)
        # Stable identity for the same recordings, independent of input ordering.
        identity = first.session_group_id or sha256('|'.join(a.id or f'{utc(a.started_at)}:{a.duration_seconds}' for a in group).encode()).hexdigest()[:24]
        explicit = first.match_reviewed or first.matched_workout_id is not None
        status = ('confirmed' if first.matched_workout_id else 'unplanned') if explicit else 'pending'
        sessions.append(ActivitySession(identity, day, tuple(group), status, first.matched_workout_id, candidates))
    claimed = {s.workout_id for s in sessions if s.workout_id}
    for day in {s.local_date for s in sessions}:
        pending = [s for s in sessions if s.local_date == day and s.status == 'pending']
        candidates = tuple(w for w in workouts if w.scheduled_for == day and w.workout_type in RUNNING_WORKOUT_TYPES and w.id not in claimed)
        for s in pending:
            if len(pending) == len(candidates) == 1:
                resolved = replace(s, status='automatic', workout_id=candidates[0].id)
            else:
                resolved = replace(s, status='needs_review' if candidates else 'unplanned')
            sessions[sessions.index(s)] = resolved
    return tuple(sorted(sessions, key=lambda s: utc(s.activities[0].started_at)))
