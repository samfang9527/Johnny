from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Callable, Literal, Protocol

from src.application.async_agent_runs import QueuedAgentRun
from src.domain.agent_runtime import AgentRun
from src.domain.athlete_race import AthleteProfile, RaceGoal
from src.domain.training_plan import TrainingPlan
from src.domain.training_plan_regeneration import (
    RegenerationQuota,
    RegenerationStrategy,
    athlete_local_day,
    calculate_regeneration_quota,
    choose_regeneration_strategy,
    decide_regeneration_admission,
    in_flight_run,
)


BACKGROUND_RACE_STATUSES = frozenset({"planned", "active"})


@dataclass(frozen=True)
class RegenerationRequest:
    client_request_id: str
    plan_type: Literal["race", "maintenance"]
    race_id: str | None = None


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


class RegenerationProfiles(Protocol):
    def get_profile_for_user(self, user_id: str) -> AthleteProfile | None: ...


class RegenerationRaceGoals(Protocol):
    def list_race_goals_for_user(self, user_id: str, *, race_date_from: date) -> list[RaceGoal]: ...


class RegenerationPlans(Protocol):
    def get_current_plan_for_user(self, user_id: str) -> TrainingPlan | None: ...


class RegenerationRuns(Protocol):
    def list_runs_for_user(self, user_id: str, *, workflow_name: str) -> list[AgentRun]: ...


class RegenerationQueue(Protocol):
    def queue_run(
        self, *, user_id: str, workflow_name: str, trigger_type: str,
        idempotency_key: str, payload: dict, requeue_terminal: bool,
    ) -> QueuedAgentRun: ...


def _manual_state(
    *, user_id: str, today: date, profiles: RegenerationProfiles,
    race_goals: RegenerationRaceGoals, runs: RegenerationRuns,
    current_instant: Callable[[], datetime],
) -> tuple[date, list[RaceGoal], list[AgentRun], RegenerationQuota]:
    profile = profiles.get_profile_for_user(user_id)
    instant = current_instant()
    athlete_today = athlete_local_day(instant, profile, today)
    races = race_goals.list_race_goals_for_user(user_id, race_date_from=athlete_today + timedelta(days=1))
    user_runs = runs.list_runs_for_user(user_id, workflow_name="training_plan_generation")
    quota = calculate_regeneration_quota(user_runs, profile, current_instant=instant, fallback_today=today)
    return athlete_today, races, user_runs, quota


class GetRegenerationOptionsHandler:
    def __init__(
        self, *, profiles: RegenerationProfiles, race_goals: RegenerationRaceGoals,
        training_plans: RegenerationPlans | None, runs: RegenerationRuns,
        current_instant: Callable[[], datetime] | None = None,
    ) -> None:
        self._profiles = profiles
        self._race_goals = race_goals
        self._training_plans = training_plans
        self._runs = runs
        self._current_instant = current_instant or (lambda: datetime.now(timezone.utc))

    def handle(self, *, user_id: str, today: date) -> RegenerationOptions:
        athlete_today, races, runs, quota = _manual_state(
            user_id=user_id, today=today, profiles=self._profiles,
            race_goals=self._race_goals, runs=self._runs, current_instant=self._current_instant,
        )
        race_id = None
        if self._training_plans is not None:
            plan = self._training_plans.get_current_plan_for_user(user_id)
            if plan is not None and plan.user_id == user_id:
                race_id = next((race.id for race in races if race.user_id == user_id and race.id == plan.race_id), None)
        strategy = choose_regeneration_strategy(
            races, starts_on=athlete_today + timedelta(days=1),
            explicit_race_id=race_id, force_maintenance=False,
        )
        in_flight = in_flight_run(runs)
        return RegenerationOptions(
            quota=quota, default_strategy=strategy,
            in_flight_run=_run_reference(in_flight) if in_flight is not None else None,
        )


class StartRegenerationHandler:
    def __init__(
        self, *, profiles: RegenerationProfiles, race_goals: RegenerationRaceGoals,
        runs: RegenerationRuns,
        queue_agent_runs: RegenerationQueue, lock_user: Callable[[str], None],
        current_instant: Callable[[], datetime] | None = None,
    ) -> None:
        self._profiles = profiles
        self._race_goals = race_goals
        self._runs = runs
        self._queue_agent_runs = queue_agent_runs
        self._lock_user = lock_user
        self._current_instant = current_instant or (lambda: datetime.now(timezone.utc))

    def handle(self, *, user_id: str, request: RegenerationRequest, today: date) -> RegenerationStartResult:
        self._lock_user(user_id)
        athlete_today, races, runs, quota = _manual_state(
            user_id=user_id, today=today, profiles=self._profiles,
            race_goals=self._race_goals, runs=self._runs, current_instant=self._current_instant,
        )
        strategy = choose_regeneration_strategy(
            races, starts_on=athlete_today + timedelta(days=1),
            explicit_race_id=request.race_id, force_maintenance=request.plan_type == "maintenance",
        )
        admission = decide_regeneration_admission(runs, quota, request.client_request_id)
        if admission.action == "reuse":
            existing_run = admission.existing_run
            assert existing_run is not None
            is_same_request = (
                existing_run.metadata.get("manual_regeneration") is True
                and existing_run.metadata.get("client_request_id") == request.client_request_id
            )
            in_flight = existing_run if existing_run.status in {"queued", "started"} and not is_same_request else None
            return RegenerationStartResult(
                quota=quota, default_strategy=strategy,
                in_flight_run=_run_reference(in_flight) if in_flight is not None else None,
                run=_run_reference(existing_run),
            )
        if admission.action == "unavailable" or strategy.reason == "explicit_race_unavailable":
            return RegenerationStartResult(quota=quota, default_strategy=strategy, in_flight_run=None, run=None)

        queued = self._queue_agent_runs.queue_run(
            user_id=user_id, workflow_name="training_plan_generation", trigger_type="manual",
            idempotency_key=_training_plan_execution_key(user_id),
            payload={
                "race_id": strategy.race_id,
                "plan_type": strategy.plan_type,
                "starts_on": strategy.starts_on.isoformat(),
                "plan_horizon_weeks": strategy.plan_horizon_weeks,
                "client_request_id": request.client_request_id,
                "manual_regeneration": True,
                "quota_day": quota.quota_day.isoformat(),
            },
            requeue_terminal=True,
        )
        run = RegenerationRun(
            run_id=queued.run.id or "", status=queued.run.status,
            workflow_name=queued.run.workflow_name, poll_url=queued.poll_url,
        )
        return RegenerationStartResult(quota=quota, default_strategy=strategy, in_flight_run=run, run=run)


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
        return GetRegenerationOptionsHandler(
            profiles=self._profiles, race_goals=self._race_goals,
            training_plans=self._training_plans, runs=self._runs,
            current_instant=self._current_instant,
        ).handle(user_id=user_id, today=today)

    def start(
        self,
        user_id: str,
        request: RegenerationRequest,
        today: date,
    ) -> RegenerationStartResult:
        return StartRegenerationHandler(
            profiles=self._profiles, race_goals=self._race_goals,
            runs=self._runs,
            queue_agent_runs=self._queue_agent_runs, lock_user=lambda user_id: None,
            current_instant=self._current_instant,
        ).handle(user_id=user_id, request=request, today=today)

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
            athlete_today = athlete_local_day(current_instant, profiles_by_user.get(plan.user_id), today)
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
            strategy = choose_regeneration_strategy(
                [
                    race
                    for race in races_by_user.get(plan.user_id, ())
                    if race.race_date >= starts_on and race.status in BACKGROUND_RACE_STATUSES
                ],
                starts_on=starts_on,
                explicit_race_id=None,
                force_maintenance=False,
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
        in_flight = in_flight_run(self._user_runs(candidate.user_id))
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
                "previous_ends_on": candidate.previous_ends_on.isoformat(),
            },
            requeue_terminal=True,
        )

    def refresh_background_strategy(
        self,
        *,
        user_id: str,
        previous_ends_on: date,
    ) -> RegenerationStrategy:
        current_instant = self._current_instant()
        profile = self._profiles.get_profile_for_user(user_id)
        athlete_today = athlete_local_day(current_instant, profile, current_instant.date())
        starts_on = max(previous_ends_on + timedelta(days=8), athlete_today + timedelta(days=1))
        races = self._race_goals.list_race_goals_for_users(
            [user_id],
            race_date_from=starts_on,
            statuses=tuple(sorted(BACKGROUND_RACE_STATUSES)),
        )
        return choose_regeneration_strategy(
            races, starts_on=starts_on,
            explicit_race_id=None,
            force_maintenance=False,
        )

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


def _run_reference(run: AgentRun) -> RegenerationRun:
    return RegenerationRun(
        run_id=run.id or "",
        status=run.status,
        workflow_name=run.workflow_name,
        poll_url=f"/api/v1/agent-runs/{run.id}",
    )
