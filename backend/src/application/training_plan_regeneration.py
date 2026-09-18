from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from math import ceil
from typing import Callable
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from src.api.schemas.training_plan_regeneration import TrainingPlanRegenerationRequest
from src.application.training_plan_generation import projection_window, select_race_strategy
from src.domain.agent_runtime import AgentRun
from src.domain.athlete_race import AthleteProfile, RaceGoal


MANUAL_REGENERATION_LIMIT = 1
IN_FLIGHT_STATUSES = frozenset({"queued", "started"})


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
class RegenerationRun:
    run_id: str
    status: str
    workflow_name: str
    poll_url: str


@dataclass(frozen=True)
class RegenerationOptions:
    quota: RegenerationQuota
    default_strategy: RegenerationStrategy
    in_flight_run: RegenerationRun | None
    run: RegenerationRun | None = None


@dataclass(frozen=True)
class RegenerationStartResult:
    quota: RegenerationQuota
    default_strategy: RegenerationStrategy
    in_flight_run: RegenerationRun | None
    run: RegenerationRun | None


class TrainingPlanRegenerationService:
    def __init__(
        self,
        *,
        profiles,
        race_goals,
        runs,
        tasks,
        queue_agent_runs,
        current_instant: Callable[[], datetime] | None = None,
    ) -> None:
        self._profiles = profiles
        self._race_goals = race_goals
        self._runs = runs
        self._tasks = tasks
        self._queue_agent_runs = queue_agent_runs
        self._current_instant = current_instant or (lambda: datetime.now(timezone.utc))

    def options(self, user_id: str, today: date) -> RegenerationOptions:
        profile = self._profiles.get_profile_for_user(user_id)
        athlete_today = _athlete_local_day(self._current_instant(), profile, today)
        races = self._future_races(user_id, athlete_today + timedelta(days=1))
        runs = self._user_runs(user_id)
        quota = _quota(runs, athlete_today, profile)
        strategy = _strategy(races, athlete_today, explicit_race_id=None, force_maintenance=False)
        in_flight = _in_flight_run(runs)
        return RegenerationOptions(
            quota=quota,
            default_strategy=strategy,
            in_flight_run=_run_reference(in_flight) if in_flight is not None else None,
        )

    def start(
        self,
        user_id: str,
        request: TrainingPlanRegenerationRequest,
        today: date,
    ) -> RegenerationStartResult:
        profile = self._profiles.get_profile_for_user(user_id)
        athlete_today = _athlete_local_day(self._current_instant(), profile, today)
        races = self._future_races(user_id, athlete_today + timedelta(days=1))
        runs = self._user_runs(user_id)
        quota = _quota(runs, athlete_today, profile)
        strategy = _strategy(
            races,
            athlete_today,
            explicit_race_id=request.race_id,
            force_maintenance=request.plan_type == "maintenance",
        )
        idempotency_key = (
            f"training_plan_regeneration:{user_id}:{quota.quota_day.isoformat()}:{request.client_request_id}"
        )
        existing_run = self._run_for_idempotency_key(idempotency_key, runs)
        if existing_run is not None:
            return RegenerationStartResult(
                quota=quota,
                default_strategy=strategy,
                in_flight_run=None,
                run=_run_reference(existing_run),
            )
        in_flight = _in_flight_run(runs)
        if in_flight is not None:
            run = _run_reference(in_flight)
            return RegenerationStartResult(
                quota=quota,
                default_strategy=strategy,
                in_flight_run=run,
                run=run,
            )
        if not quota.available:
            return RegenerationStartResult(
                quota=quota,
                default_strategy=strategy,
                in_flight_run=None,
                run=None,
            )

        payload = {
            "race_id": strategy.race_id,
            "plan_type": strategy.plan_type,
            "starts_on": strategy.starts_on.isoformat(),
            "plan_horizon_weeks": strategy.plan_horizon_weeks,
            "client_request_id": request.client_request_id,
            "manual_regeneration": True,
            "quota_day": quota.quota_day.isoformat(),
        }
        queued = self._queue_agent_runs.queue_run(
            user_id=user_id,
            workflow_name="training_plan_generation",
            trigger_type="manual",
            idempotency_key=idempotency_key,
            payload=payload,
        )
        run = RegenerationRun(
            run_id=queued.run.id or "",
            status=queued.run.status,
            workflow_name=queued.run.workflow_name,
            poll_url=queued.poll_url,
        )
        return RegenerationStartResult(
            quota=quota,
            default_strategy=strategy,
            in_flight_run=run,
            run=run,
        )

    def _future_races(self, user_id: str, starts_on: date) -> list[RaceGoal]:
        return self._race_goals.list_race_goals_for_user(user_id, race_date_from=starts_on)

    def _user_runs(self, user_id: str) -> list[AgentRun]:
        return self._runs.list_runs_for_user(user_id, workflow_name="training_plan_generation")

    def _run_for_idempotency_key(self, idempotency_key: str, runs: list[AgentRun]) -> AgentRun | None:
        task = self._tasks.get_by_idempotency_key(idempotency_key)
        if task is None:
            return None
        run_id = task.payload.get("run_id")
        if run_id is None:
            return None
        return next((run for run in runs if run.id == str(run_id)), None)


def _quota(runs: list[AgentRun], quota_day: date, profile: AthleteProfile | None) -> RegenerationQuota:
    used = sum(_consumes_quota(run, quota_day) for run in runs)
    remaining = max(0, MANUAL_REGENERATION_LIMIT - used)
    available = remaining > 0
    return RegenerationQuota(
        quota_day=quota_day,
        limit=MANUAL_REGENERATION_LIMIT,
        used=used,
        remaining=remaining,
        available=available,
        next_available_at=None if available else _next_available_at(quota_day, profile),
    )


def _in_flight_run(runs: list[AgentRun]) -> AgentRun | None:
    return next(
        (
            run
            for run in runs
            if run.status in IN_FLIGHT_STATUSES and run.metadata.get("manual_regeneration") is True
        ),
        None,
    )


def _athlete_local_day(current_instant: datetime, profile: AthleteProfile | None, fallback: date) -> date:
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


def _strategy(
    races: list[RaceGoal],
    today: date,
    *,
    explicit_race_id: str | None,
    force_maintenance: bool,
) -> RegenerationStrategy:
    starts_on = today + timedelta(days=1)
    race_by_id = {race.id: race for race in races}
    selection = select_race_strategy(
        [
            {
                "id": race.id,
                "race_date": race.race_date,
                "priority": race.priority,
            }
            for race in races
        ],
        anchor=starts_on,
        explicit_race_id=explicit_race_id,
        force_maintenance=force_maintenance,
    )
    selected_race = race_by_id.get(selection.race_id)
    _, ends_on = projection_window(
        starts_on,
        selected_race.race_date if selected_race is not None else None,
        selection.plan_type,
    )
    plan_horizon_weeks = ceil(((ends_on - starts_on).days + 1) / 7)
    return RegenerationStrategy(
        race_id=selection.race_id,
        plan_type=selection.plan_type,
        reason=selection.reason,
        starts_on=starts_on,
        plan_horizon_weeks=plan_horizon_weeks,
    )


def _consumes_quota(run: AgentRun, quota_day: date) -> bool:
    metadata = run.metadata or {}
    return (
        run.status == "completed"
        and metadata.get("manual_regeneration") is True
        and metadata.get("quota_day") == quota_day.isoformat()
        and bool(metadata.get("created_training_plan_id"))
    )


def _next_available_at(quota_day: date, profile: AthleteProfile | None) -> datetime:
    timezone_info = _athlete_timezone(profile) or timezone.utc
    return datetime.combine(quota_day + timedelta(days=1), time.min, tzinfo=timezone_info)


def _run_reference(run: AgentRun) -> RegenerationRun:
    return RegenerationRun(
        run_id=run.id or "",
        status=run.status,
        workflow_name=run.workflow_name,
        poll_url=f"/api/v1/agent-runs/{run.id}",
    )
