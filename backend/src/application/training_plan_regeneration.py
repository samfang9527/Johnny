from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from math import ceil
from typing import Callable
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from src.api.schemas.training_plan_regeneration import TrainingPlanRegenerationRequest
from src.application.async_agent_runs import QueuedAgentRun
from src.application.training_plan_generation import projection_window, select_race_strategy
from src.domain.agent_runtime import AgentRun
from src.domain.athlete_race import AthleteProfile, RaceGoal
from src.domain.training_plan import TrainingPlan


MANUAL_REGENERATION_LIMIT = 1
IN_FLIGHT_STATUSES = frozenset({"queued", "started"})
BACKGROUND_RACE_STATUSES = frozenset({"planned", "active"})


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


@dataclass(frozen=True)
class BackgroundProjectionCandidate:
    user_id: str
    previous_plan_id: str | None
    previous_ends_on: date
    strategy: RegenerationStrategy


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
        training_plans=None,
    ) -> None:
        self._profiles = profiles
        self._race_goals = race_goals
        self._training_plans = training_plans
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
        existing_run = _run_for_client_request_id(runs, request.client_request_id)
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
            idempotency_key=_training_plan_execution_key(user_id),
            payload=payload,
            requeue_terminal=True,
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

    def find_users_needing_projection(self, today: date) -> list[BackgroundProjectionCandidate]:
        if self._training_plans is None:
            return []

        # An athlete-local date can be one day ahead of the server date, so
        # server_today - 6 includes every plan possibly seven local days past end.
        # There is intentionally no lower bound: overdue failures remain retryable.
        candidate_plans = self._training_plans.list_active_plans_ending_on_or_before(
            today - timedelta(days=6)
        )
        latest_candidate_by_user = _latest_plan_by_user(candidate_plans)
        profiles_by_user = {
            profile.user_id: profile
            for profile in self._profiles.list_profiles_for_users(list(latest_candidate_by_user))
        }
        current_instant = self._current_instant()
        eligible_plans: list[TrainingPlan] = []
        athlete_days: dict[str, date] = {}
        for plan in latest_candidate_by_user.values():
            athlete_today = _athlete_local_day(current_instant, profiles_by_user.get(plan.user_id), today)
            if athlete_today < plan.ends_on + timedelta(days=7):
                continue
            eligible_plans.append(plan)
            athlete_days[plan.user_id] = athlete_today

        if not eligible_plans:
            return []
        projection_starts_by_user = {
            plan.user_id: max(
                plan.ends_on + timedelta(days=8),
                athlete_days[plan.user_id] + timedelta(days=1),
            )
            for plan in eligible_plans
        }
        earliest_projection_start = min(projection_starts_by_user.values())
        active_replacements_by_user = _plans_by_user(
            self._training_plans.list_active_plans_ending_on_or_after(earliest_projection_start)
        )
        races_by_user = _races_by_user(
            self._race_goals.list_race_goals_for_users(
                [plan.user_id for plan in eligible_plans],
                race_date_from=earliest_projection_start,
                statuses=tuple(sorted(BACKGROUND_RACE_STATUSES)),
            )
        )
        candidates: list[BackgroundProjectionCandidate] = []
        for plan in eligible_plans:
            athlete_today = athlete_days[plan.user_id]
            starts_on = projection_starts_by_user[plan.user_id]
            if _has_active_replacement(
                active_replacements_by_user.get(plan.user_id, ()),
                previous_plan_id=plan.id,
                starts_on=starts_on,
            ):
                continue
            strategy = _strategy(
                [
                    race
                    for race in races_by_user.get(plan.user_id, ())
                    if race.race_date >= starts_on and race.status in BACKGROUND_RACE_STATUSES
                ],
                athlete_today,
                explicit_race_id=None,
                force_maintenance=False,
                starts_on=starts_on,
            )
            candidates.append(
                BackgroundProjectionCandidate(
                    user_id=plan.user_id,
                    previous_plan_id=plan.id,
                    previous_ends_on=plan.ends_on,
                    strategy=strategy,
                )
            )
        return candidates

    def queue_background_generation(self, candidate: BackgroundProjectionCandidate) -> QueuedAgentRun:
        in_flight = _in_flight_run(self._user_runs(candidate.user_id))
        if in_flight is not None:
            return self._queued_result_for_existing_run(in_flight)

        strategy = candidate.strategy
        return self._queue_agent_runs.queue_run(
            user_id=candidate.user_id,
            workflow_name="training_plan_generation",
            trigger_type="scheduled",
            idempotency_key=_training_plan_execution_key(candidate.user_id),
            payload={
                "race_id": strategy.race_id,
                "plan_type": strategy.plan_type,
                "starts_on": strategy.starts_on.isoformat(),
                "plan_horizon_weeks": strategy.plan_horizon_weeks,
                "manual_regeneration": False,
                "trigger_type": "scheduled",
                "replace_active_projection": True,
            },
            requeue_terminal=True,
        )

    def _future_races(self, user_id: str, starts_on: date) -> list[RaceGoal]:
        return self._race_goals.list_race_goals_for_user(user_id, race_date_from=starts_on)

    def _user_runs(self, user_id: str) -> list[AgentRun]:
        return self._runs.list_runs_for_user(user_id, workflow_name="training_plan_generation")

    def _queued_result_for_existing_run(self, run: AgentRun) -> QueuedAgentRun:
        task = self._tasks.get_by_correlation_id(run.id or "")
        if task is None:
            raise RuntimeError(f"in-flight training plan run {run.id} has no queued task")
        return QueuedAgentRun(
            run=run,
            task=task,
            poll_url=f"/api/v1/agent-runs/{run.id}",
        )


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
            if run.status in IN_FLIGHT_STATUSES
        ),
        None,
    )


def _run_for_client_request_id(runs: list[AgentRun], client_request_id: str) -> AgentRun | None:
    return next(
        (
            run
            for run in runs
            if run.metadata.get("manual_regeneration") is True
            and run.metadata.get("client_request_id") == client_request_id
        ),
        None,
    )


def _training_plan_execution_key(user_id: str) -> str:
    return f"training_plan_generation:{user_id}"


def _latest_plan_by_user(plans: list[TrainingPlan]) -> dict[str, TrainingPlan]:
    latest: dict[str, TrainingPlan] = {}
    for plan in plans:
        current = latest.get(plan.user_id)
        if current is None or plan.ends_on > current.ends_on:
            latest[plan.user_id] = plan
    return latest


def _plans_by_user(plans) -> dict[str, tuple]:
    plans_by_user: dict[str, list] = {}
    for plan in plans:
        plans_by_user.setdefault(plan.user_id, []).append(plan)
    return {user_id: tuple(user_plans) for user_id, user_plans in plans_by_user.items()}


def _races_by_user(races: list[RaceGoal]) -> dict[str, tuple[RaceGoal, ...]]:
    races_by_user: dict[str, list[RaceGoal]] = {}
    for race in races:
        races_by_user.setdefault(race.user_id, []).append(race)
    return {user_id: tuple(user_races) for user_id, user_races in races_by_user.items()}


def _has_active_replacement(plans, *, previous_plan_id: str | None, starts_on: date) -> bool:
    return any(
        plan.id != previous_plan_id and plan.ends_on >= starts_on
        for plan in plans
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
    starts_on: date | None = None,
) -> RegenerationStrategy:
    starts_on = starts_on or today + timedelta(days=1)
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
