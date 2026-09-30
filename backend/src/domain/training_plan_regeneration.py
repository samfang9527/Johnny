from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timezone, timedelta
from math import ceil
from typing import Literal, Sequence
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from src.domain.agent_runtime import AgentRun
from src.domain.athlete_race import AthleteProfile, RaceGoal


MANUAL_REGENERATION_LIMIT = 1
IN_FLIGHT_STATUSES = frozenset({"queued", "started"})
RACE_PRIORITY_RANK = {"primary": 0, "secondary": 1, "tune_up": 2}


@dataclass(frozen=True)
class RaceStrategySelection:
    race_id: str | None
    plan_type: str
    reason: str


@dataclass(frozen=True)
class RegenerationQuota:
    quota_day: date
    limit: int
    used: int
    remaining: int
    available: bool
    next_available_at: datetime | None


@dataclass(frozen=True)
class RegenerationStrategy:
    race_id: str | None
    plan_type: str
    reason: str
    starts_on: date
    plan_horizon_weeks: int


@dataclass(frozen=True)
class RegenerationAdmission:
    action: Literal["reuse", "queue", "unavailable"]
    existing_run: AgentRun | None


def select_race_strategy(
    race_goals: Sequence[dict],
    anchor: date,
    explicit_race_id: str | None,
    force_maintenance: bool,
) -> RaceStrategySelection:
    if force_maintenance:
        return RaceStrategySelection(None, "maintenance", "maintenance_forced")

    future_races = [race for race in race_goals if _race_date(race) >= anchor]
    if explicit_race_id is not None:
        if any(race.get("id") == explicit_race_id for race in future_races):
            return RaceStrategySelection(explicit_race_id, "race", "explicit_race")
        return RaceStrategySelection(None, "maintenance", "explicit_race_unavailable")

    ranked_races = [race for race in future_races if race.get("priority") in RACE_PRIORITY_RANK]
    if not ranked_races:
        return RaceStrategySelection(None, "maintenance", "no_future_race")
    selected = min(ranked_races, key=lambda race: (RACE_PRIORITY_RANK[race["priority"]], _race_date(race)))
    return RaceStrategySelection(selected.get("id"), "race", "priority_and_date")


def projection_window(anchor: date, race_date: date | None, plan_type: str) -> tuple[date, date]:
    if plan_type == "maintenance":
        return anchor, anchor + timedelta(weeks=4) - timedelta(days=1)
    if plan_type != "race":
        raise ValueError(f"unsupported plan type: {plan_type}")
    if race_date is None:
        raise ValueError("race plan requires a race date")
    horizon_end = anchor + timedelta(weeks=16) - timedelta(days=1)
    return anchor, min(race_date, horizon_end)


def choose_regeneration_strategy(
    races: Sequence[RaceGoal], *, starts_on: date,
    explicit_race_id: str | None, force_maintenance: bool,
) -> RegenerationStrategy:
    race_by_id = {race.id: race for race in races}
    selection = select_race_strategy(
        [{"id": race.id, "race_date": race.race_date, "priority": race.priority} for race in races],
        anchor=starts_on, explicit_race_id=explicit_race_id,
        force_maintenance=force_maintenance,
    )
    selected_race = race_by_id.get(selection.race_id)
    _, ends_on = projection_window(
        starts_on, selected_race.race_date if selected_race is not None else None,
        selection.plan_type,
    )
    return RegenerationStrategy(
        race_id=selection.race_id, plan_type=selection.plan_type, reason=selection.reason,
        starts_on=starts_on, plan_horizon_weeks=ceil(((ends_on - starts_on).days + 1) / 7),
    )


def calculate_regeneration_quota(
    runs: Sequence[AgentRun], profile: AthleteProfile | None, *,
    current_instant: datetime, fallback_today: date,
) -> RegenerationQuota:
    quota_day = athlete_local_day(current_instant, profile, fallback_today)
    used = sum(_consumes_quota(run, quota_day, profile) for run in runs)
    remaining = max(0, MANUAL_REGENERATION_LIMIT - used)
    available = remaining > 0
    timezone_info = _athlete_timezone(profile) or timezone.utc
    return RegenerationQuota(
        quota_day=quota_day, limit=MANUAL_REGENERATION_LIMIT, used=used,
        remaining=remaining, available=available,
        next_available_at=None if available else datetime.combine(
            quota_day + timedelta(days=1), time.min, tzinfo=timezone_info,
        ),
    )


def decide_regeneration_admission(
    runs: Sequence[AgentRun], quota: RegenerationQuota, client_request_id: str,
) -> RegenerationAdmission:
    original = next((
        run for run in runs
        if run.metadata.get("manual_regeneration") is True
        and run.metadata.get("client_request_id") == client_request_id
    ), None)
    if original is not None:
        return RegenerationAdmission("reuse", original)
    in_flight = in_flight_run(runs)
    if in_flight is not None:
        return RegenerationAdmission("reuse", in_flight)
    if not quota.available:
        return RegenerationAdmission("unavailable", None)
    return RegenerationAdmission("queue", None)


def in_flight_run(runs: Sequence[AgentRun]) -> AgentRun | None:
    return next((run for run in runs if run.status in IN_FLIGHT_STATUSES), None)


def athlete_local_day(current_instant: datetime, profile: AthleteProfile | None, fallback: date) -> date:
    timezone_info = _athlete_timezone(profile)
    if timezone_info is None:
        return fallback
    if current_instant.tzinfo is None:
        current_instant = current_instant.replace(tzinfo=timezone.utc)
    return current_instant.astimezone(timezone_info).date()


def _athlete_timezone(profile: AthleteProfile | None) -> ZoneInfo | None:
    if profile is None:
        return None
    try:
        return ZoneInfo(profile.timezone)
    except (ZoneInfoNotFoundError, ValueError):
        return None


def _consumes_quota(run: AgentRun, quota_day: date, profile: AthleteProfile | None) -> bool:
    if run.finished_at is None:
        return False
    instant = run.finished_at
    if instant.tzinfo is None:
        instant = instant.replace(tzinfo=timezone.utc)
    completed_day = instant.astimezone(_athlete_timezone(profile)).date()
    metadata = run.metadata or {}
    return (
        run.status == "completed" and metadata.get("manual_regeneration") is True
        and completed_day == quota_day and bool(metadata.get("created_training_plan_id"))
    )


def _race_date(race: dict) -> date:
    race_date = race["race_date"]
    return race_date if isinstance(race_date, date) else date.fromisoformat(race_date)
