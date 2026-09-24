from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timedelta, timezone

from src.api.schemas.training_plan_regeneration import TrainingPlanRegenerationRequest
from src.application.async_agent_runs import QueueAgentRunHandler
from src.application.interfaces.task_queue import AgentTask, TaskEnvelope
from src.application.training_plan_regeneration import TrainingPlanRegenerationService
from src.domain.agent_runtime import AgentRun
from src.domain.athlete_race import AthleteProfile, RaceGoal
from src.domain.training_plan import TrainingPlan


TODAY = date(2026, 9, 17)
CURRENT_INSTANT = datetime(2026, 9, 17, 12, tzinfo=timezone.utc)


def test_options_uses_athlete_timezone_for_next_quota_availability() -> None:
    service, runs, _ = _service(profile=_profile(timezone_name="Asia/Taipei"))
    runs.add(_completed_manual_run(quota_day=TODAY, created_plan_id="plan-1"))

    options = service.options("athlete-1", TODAY)

    assert options.quota.available is False
    assert options.quota.quota_day == TODAY
    assert options.quota.next_available_at.isoformat() == "2026-09-18T00:00:00+08:00"


def test_athlete_local_day_drives_quota_races_and_start_date() -> None:
    athlete_day = date(2026, 9, 17)
    service, _, tasks = _service(
        profile=_profile(timezone_name="America/Los_Angeles"),
        races=[_race("local-tomorrow", date(2026, 9, 18))],
        current_instant=datetime(2026, 9, 18, 0, 30, tzinfo=timezone.utc),
    )

    options = service.options("athlete-1", date(2026, 9, 18))
    result = service.start("athlete-1", _request("date-boundary"), date(2026, 9, 18))

    assert options.quota.quota_day == athlete_day
    assert options.default_strategy.race_id == "local-tomorrow"
    assert options.default_strategy.starts_on == date(2026, 9, 18)
    assert result.run is not None
    assert tasks.items[0].idempotency_key == _execution_key()
    assert tasks.items[0].payload["input"]["quota_day"] == "2026-09-17"
    assert tasks.items[0].payload["input"]["starts_on"] == "2026-09-18"


def test_one_successful_manual_regeneration_consumes_the_daily_quota() -> None:
    service, runs, tasks = _service()
    runs.add(_completed_manual_run(quota_day=TODAY, created_plan_id="plan-1"))

    result = service.start("athlete-1", _request("new-confirmation"), TODAY)

    assert result.quota.used == 1
    assert result.quota.remaining == 0
    assert result.run is None
    assert tasks.items == []


def test_failed_manual_regeneration_does_not_consume_quota() -> None:
    service, runs, tasks = _service()
    runs.add(
        AgentRun(
            id="failed-run",
            user_id="athlete-1",
            trigger_type="manual",
            workflow_name="training_plan_generation",
            prompt_version="v1",
            status="failed",
            error_type="generation_error",
            error_message="could not generate plan",
            metadata={"manual_regeneration": True, "quota_day": TODAY.isoformat()},
        )
    )

    result = service.start("athlete-1", _request("retry-after-failure"), TODAY)

    assert result.quota.available is True
    assert result.run is not None
    assert len(tasks.items) == 1


def test_start_reuses_an_existing_in_flight_manual_run() -> None:
    service, runs, tasks = _service()
    runs.add(
        AgentRun.queue(
            id="run-in-flight",
            user_id="athlete-1",
            trigger_type="manual",
            workflow_name="training_plan_generation",
            prompt_version="v1",
            metadata={"manual_regeneration": True, "quota_day": TODAY.isoformat()},
        )
    )

    result = service.start("athlete-1", _request("another-confirmation"), TODAY)

    assert result.run is not None
    assert result.run.run_id == "run-in-flight"
    assert result.in_flight_run == result.run
    assert tasks.items == []


def test_start_reuses_an_existing_in_flight_scheduled_run() -> None:
    plan = _active_plan(ends_on=date(2026, 9, 10))
    service, _, tasks = _service(plans=[plan])
    candidate = service.find_users_needing_projection(TODAY)[0]
    scheduled = service.queue_background_generation(candidate)

    result = service.start("athlete-1", _request("manual-while-scheduled"), TODAY)

    assert result.run is not None
    assert result.run.run_id == scheduled.run.id
    assert result.in_flight_run == result.run
    assert len(tasks.items) == 1


def test_client_request_id_retry_returns_the_same_failed_run() -> None:
    service, runs, tasks = _service()
    request = _request("request-123")

    first = service.start("athlete-1", request, TODAY)
    assert first.run is not None
    tasks.set_status(_execution_key(), "failed")
    runs.set_status(first.run.run_id, "failed")
    second = service.start("athlete-1", request, TODAY)

    assert second.run is not None
    assert second.run.run_id == first.run.run_id
    assert second.run.status == "failed"
    assert len(tasks.items) == 1


def test_client_request_id_retry_returns_terminal_run_while_another_run_is_in_flight() -> None:
    service, runs, tasks = _service()
    retried_request = _request("request-a")

    terminal = service.start("athlete-1", retried_request, TODAY)
    assert terminal.run is not None
    tasks.set_status(_execution_key(), "failed")
    runs.set_status(terminal.run.run_id, "failed")
    in_flight = service.start("athlete-1", _request("request-b"), TODAY)
    assert in_flight.run is not None

    retried = service.start("athlete-1", retried_request, TODAY)

    assert retried.run is not None
    assert retried.run.run_id == terminal.run.run_id
    assert retried.run.status == "failed"
    assert retried.run.run_id != in_flight.run.run_id
    assert len(tasks.items) == 1


def test_client_request_id_retry_returns_the_same_completed_run_before_quota_blocking() -> None:
    service, runs, tasks = _service()
    request = _request("completed-request")

    first = service.start("athlete-1", request, TODAY)
    assert first.run is not None
    tasks.set_status(_execution_key(), "completed")
    runs.set_status(
        first.run.run_id,
        "completed",
        metadata_updates={"created_training_plan_id": "plan-completed"},
    )
    second = service.start("athlete-1", request, TODAY)

    assert second.quota.available is False
    assert second.run is not None
    assert second.run.run_id == first.run.run_id
    assert second.run.status == "completed"
    assert len(tasks.items) == 1


def test_different_client_request_id_queues_a_new_run_after_failure() -> None:
    service, runs, tasks = _service()

    first = service.start("athlete-1", _request("failed-request"), TODAY)
    assert first.run is not None
    tasks.set_status(_execution_key(), "failed")
    runs.set_status(first.run.run_id, "failed")
    second = service.start("athlete-1", _request("new-request"), TODAY)

    assert second.run is not None
    assert second.run.run_id != first.run.run_id
    assert len(tasks.items) == 1
    assert tasks.items[0].idempotency_key == _execution_key()
    assert tasks.items[0].payload["run_id"] == second.run.run_id


def test_options_and_start_select_maintenance_without_a_future_race() -> None:
    service, _, tasks = _service(races=[_race("past-race", date(2026, 9, 16))])

    options = service.options("athlete-1", TODAY)
    result = service.start("athlete-1", _request("maintenance", plan_type="maintenance"), TODAY)

    assert options.default_strategy.plan_type == "maintenance"
    assert options.default_strategy.race_id is None
    assert result.default_strategy.plan_type == "maintenance"
    assert tasks.items[0].payload["input"] == {
        "race_id": None,
        "plan_type": "maintenance",
        "starts_on": "2026-09-18",
        "plan_horizon_weeks": 4,
        "client_request_id": "maintenance",
        "manual_regeneration": True,
        "quota_day": "2026-09-17",
    }


def test_background_candidates_skip_active_and_recovery_window_projections() -> None:
    plan = _active_plan(ends_on=date(2026, 9, 10))

    for today in (date(2026, 9, 9), *[date(2026, 9, day) for day in range(11, 17)]):
        service, _, _ = _service(
            plans=[plan],
            current_instant=datetime(today.year, today.month, today.day, 12, tzinfo=timezone.utc),
        )
        assert service.find_users_needing_projection(today) == []


def test_background_candidate_queues_scheduled_race_plan_after_recovery_week() -> None:
    plan = _active_plan(ends_on=date(2026, 9, 10))
    service, _, tasks = _service(
        plans=[plan],
        races=[
            _race("secondary-near", date(2026, 10, 15), priority="secondary"),
            _race("primary-far", date(2026, 11, 15), priority="primary"),
        ],
    )

    candidates = service.find_users_needing_projection(date(2026, 9, 17))
    queued = service.queue_background_generation(candidates[0])

    assert len(candidates) == 1
    assert candidates[0].previous_plan_id == plan.id
    assert candidates[0].strategy.race_id == "primary-far"
    assert candidates[0].strategy.plan_type == "race"
    assert candidates[0].strategy.starts_on == date(2026, 9, 18)
    assert queued.run.trigger_type == "scheduled"
    assert tasks.items[0].idempotency_key == _execution_key()
    assert tasks.items[0].payload["input"] == {
        "race_id": "primary-far",
        "plan_type": "race",
        "starts_on": "2026-09-18",
        "plan_horizon_weeks": 9,
        "manual_regeneration": False,
        "trigger_type": "scheduled",
        "replace_active_projection": True,
        "previous_ends_on": "2026-09-10",
    }
    assert queued.run.metadata["previous_ends_on"] == "2026-09-10"


def test_background_candidate_uses_maintenance_when_no_future_race_exists() -> None:
    service, _, _ = _service(
        plans=[_active_plan(ends_on=date(2026, 9, 10))],
        races=[_race("past-race", date(2026, 9, 16))],
    )

    candidates = service.find_users_needing_projection(date(2026, 9, 17))

    assert len(candidates) == 1
    assert candidates[0].strategy.race_id is None
    assert candidates[0].strategy.plan_type == "maintenance"
    assert candidates[0].strategy.plan_horizon_weeks == 4


def test_background_queue_reuses_the_shared_user_execution_slot() -> None:
    service, _, tasks = _service(plans=[_active_plan(ends_on=date(2026, 9, 10))])
    candidate = service.find_users_needing_projection(date(2026, 9, 17))[0]

    first = service.queue_background_generation(candidate)
    second = service.queue_background_generation(candidate)

    assert second.run.id == first.run.id
    assert len(tasks.items) == 1
    assert tasks.items[0].idempotency_key == _execution_key()


def test_background_queue_reuses_an_in_flight_manual_generation() -> None:
    plan = _active_plan(ends_on=date(2026, 9, 10))
    service, _, tasks = _service(plans=[plan])
    manual = service.start("athlete-1", _request("manual-before-daily-check"), TODAY)
    candidate = service.find_users_needing_projection(TODAY)[0]

    scheduled = service.queue_background_generation(candidate)

    assert manual.run is not None
    assert scheduled.run.id == manual.run.run_id
    assert len(tasks.items) == 1
    assert tasks.items[0].payload["input"]["manual_regeneration"] is True


def test_background_queue_retries_after_a_terminal_failure() -> None:
    service, runs, tasks = _service(plans=[_active_plan(ends_on=date(2026, 9, 10))])
    candidate = service.find_users_needing_projection(TODAY)[0]
    first = service.queue_background_generation(candidate)
    tasks.set_status(first.task.idempotency_key, "dead_lettered")
    runs.set_status(first.run.id or "", "failed")

    retried = service.queue_background_generation(candidate)

    assert retried.run.id != first.run.id
    assert len(tasks.items) == 1
    assert retried.task.id == first.task.id
    assert tasks.items[0].idempotency_key == _execution_key()
    assert tasks.items[0].payload["run_id"] == retried.run.id


def test_background_candidate_remains_eligible_after_day_seven_for_terminal_retries() -> None:
    plan = _active_plan(ends_on=date(2026, 9, 10))
    retry_day = date(2026, 9, 20)
    service, _, _ = _service(
        plans=[plan],
        races=[
            _race("already-past", date(2026, 9, 20), priority="primary"),
            _race("retry-race", date(2026, 9, 28), priority="secondary"),
        ],
        current_instant=datetime(2026, 9, 20, 12, tzinfo=timezone.utc),
    )

    candidates = service.find_users_needing_projection(retry_day)

    assert len(candidates) == 1
    assert candidates[0].previous_plan_id == plan.id
    assert candidates[0].strategy.starts_on == date(2026, 9, 21)
    assert candidates[0].strategy.race_id == "retry-race"


def test_background_candidate_ignores_completed_and_cancelled_races() -> None:
    service, _, _ = _service(
        plans=[_active_plan(ends_on=date(2026, 9, 10))],
        races=[
            _race("cancelled-primary", date(2026, 10, 20), priority="primary", status="cancelled"),
            _race("completed-secondary", date(2026, 10, 10), priority="secondary", status="completed"),
            _race("planned-tune-up", date(2026, 10, 5), priority="tune_up", status="planned"),
        ],
    )

    candidates = service.find_users_needing_projection(date(2026, 9, 17))

    assert len(candidates) == 1
    assert candidates[0].strategy.race_id == "planned-tune-up"


def test_background_execution_refresh_rebases_start_and_reselects_current_race_strategy() -> None:
    execution_day = date(2026, 9, 20)
    service, _, _ = _service(
        races=[
            _race("queued-primary", date(2026, 10, 1), priority="primary", status="cancelled"),
            _race("active-secondary", date(2026, 10, 5), priority="secondary", status="active"),
            _race("planned-primary", date(2026, 11, 15), priority="primary", status="planned"),
        ],
        current_instant=datetime(2026, 9, 20, 12, tzinfo=timezone.utc),
    )

    refreshed = service.refresh_background_strategy(
        user_id="athlete-1",
        previous_ends_on=date(2026, 9, 10),
    )

    assert refreshed.starts_on == execution_day + timedelta(days=1)
    assert refreshed.race_id == "planned-primary"
    assert refreshed.plan_type == "race"
    assert refreshed.plan_horizon_weeks == 8


def test_background_candidate_is_skipped_when_an_active_replacement_covers_its_start() -> None:
    previous = _active_plan(ends_on=date(2026, 9, 10))
    replacement = TrainingPlan.create(
        id="replacement-plan",
        user_id="athlete-1",
        name="Replacement",
        starts_on=date(2026, 9, 17),
        ends_on=date(2026, 10, 14),
        status="active",
    )
    service, _, _ = _service(plans=[previous, replacement])

    assert service.find_users_needing_projection(TODAY) == []


def test_background_candidate_is_skipped_when_an_active_replacement_starts_later() -> None:
    previous = _active_plan(ends_on=date(2026, 9, 10))
    replacement = TrainingPlan.create(
        id="replacement-plan",
        user_id="athlete-1",
        name="Replacement",
        starts_on=date(2026, 9, 25),
        ends_on=date(2026, 10, 22),
        status="active",
    )
    service, _, _ = _service(plans=[previous, replacement])

    assert service.find_users_needing_projection(TODAY) == []


def test_background_candidate_uses_the_athletes_local_date() -> None:
    service, _, _ = _service(
        profile=_profile(timezone_name="America/Los_Angeles"),
        plans=[_active_plan(ends_on=date(2026, 9, 10))],
        current_instant=datetime(2026, 9, 18, 0, 30, tzinfo=timezone.utc),
    )

    candidates = service.find_users_needing_projection(date(2026, 9, 18))

    assert len(candidates) == 1
    assert candidates[0].strategy.starts_on == date(2026, 9, 18)


def _service(
    *,
    profile: AthleteProfile | None = None,
    races: list[RaceGoal] | None = None,
    plans: list[TrainingPlan] | None = None,
    current_instant: datetime = CURRENT_INSTANT,
) -> tuple[TrainingPlanRegenerationService, "_FakeRunStore", "_FakeTaskQueue"]:
    profiles = _FakeProfiles(profile or _profile())
    race_store = _FakeRaces(races or [_race("race-primary", date(2026, 12, 20))])
    runs = _FakeRunStore()
    tasks = _FakeTaskQueue()
    return (
        TrainingPlanRegenerationService(
            profiles=profiles,
            race_goals=race_store,
            training_plans=_FakePlans(plans or []),
            runs=runs,
            tasks=tasks,
            queue_agent_runs=QueueAgentRunHandler(
                runs=runs,
                queue=tasks,
                prompt_version="v1",
            ),
            current_instant=lambda: current_instant,
        ),
        runs,
        tasks,
    )


def _profile(*, timezone_name: str = "UTC") -> AthleteProfile:
    return AthleteProfile.create(
        user_id="athlete-1",
        timezone=timezone_name,
        experience_level="intermediate",
        current_weekly_mileage_km=35,
        preferred_training_days=("tuesday", "thursday", "sunday"),
        preferred_long_run_day="sunday",
        max_runs_per_week=4,
    )


def _race(
    race_id: str,
    race_date: date,
    *,
    priority: str = "primary",
    status: str = "planned",
) -> RaceGoal:
    return RaceGoal.create(
        id=race_id,
        user_id="athlete-1",
        name="Race",
        race_date=race_date,
        distance_meters=21097,
        priority=priority,
        status=status,
    )


def _active_plan(*, ends_on: date) -> TrainingPlan:
    return TrainingPlan.create(
        id=f"plan-{ends_on.isoformat()}",
        user_id="athlete-1",
        name="Current plan",
        starts_on=ends_on - timedelta(weeks=4) + timedelta(days=1),
        ends_on=ends_on,
        status="active",
    )


def _request(client_request_id: str, *, plan_type: str = "race") -> TrainingPlanRegenerationRequest:
    return TrainingPlanRegenerationRequest(client_request_id=client_request_id, plan_type=plan_type)


def _execution_key() -> str:
    return "training_plan_generation:athlete-1"


def _completed_manual_run(*, quota_day: date, created_plan_id: str) -> AgentRun:
    return AgentRun(
        id=f"completed-{created_plan_id}",
        user_id="athlete-1",
        trigger_type="manual",
        workflow_name="training_plan_generation",
        prompt_version="v1",
        status="completed",
        finished_at=datetime(2026, 9, 17, 2, tzinfo=timezone.utc),
        metadata={
            "manual_regeneration": True,
            "quota_day": quota_day.isoformat(),
            "created_training_plan_id": created_plan_id,
        },
    )


class _FakeProfiles:
    def __init__(self, profile: AthleteProfile | None) -> None:
        self.profile = profile

    def get_profile_for_user(self, user_id: str) -> AthleteProfile | None:
        return self.profile if self.profile is not None and self.profile.user_id == user_id else None

    def list_profiles_for_users(self, user_ids: list[str]) -> list[AthleteProfile]:
        if self.profile is None or self.profile.user_id not in user_ids:
            return []
        return [self.profile]


class _FakeRaces:
    def __init__(self, races: list[RaceGoal]) -> None:
        self.races = races

    def list_race_goals_for_user(self, user_id: str, **kwargs) -> list[RaceGoal]:
        race_date_from = kwargs.get("race_date_from")
        return [
            race
            for race in self.races
            if race.user_id == user_id and (race_date_from is None or race.race_date >= race_date_from)
        ]

    def list_race_goals_for_users(self, user_ids: list[str], **kwargs) -> list[RaceGoal]:
        race_date_from = kwargs.get("race_date_from")
        statuses = kwargs.get("statuses")
        return [
            race
            for race in self.races
            if race.user_id in user_ids
            and (race_date_from is None or race.race_date >= race_date_from)
            and (statuses is None or race.status in statuses)
        ]


class _FakePlans:
    def __init__(self, plans: list[TrainingPlan]) -> None:
        self.plans = plans

    def list_active_plans_ending_on_or_before(self, ends_on: date) -> list[TrainingPlan]:
        return [
            plan
            for plan in self.plans
            if plan.status == "active" and plan.ends_on <= ends_on
        ]

    def list_active_plans_ending_on_or_after(self, ends_on: date) -> list[TrainingPlan]:
        return [
            plan
            for plan in self.plans
            if plan.status == "active" and plan.ends_on >= ends_on
        ]


class _FakeRunStore:
    def __init__(self) -> None:
        self.runs: list[AgentRun] = []

    def add(self, run: AgentRun) -> AgentRun:
        self.runs.insert(0, run)
        return run

    def create_run(self, run: AgentRun) -> AgentRun:
        created = replace(run, id=run.id or f"run-{len(self.runs) + 1}")
        return self.add(created)

    def get_run_for_user(self, user_id: str, run_id: str | None) -> AgentRun | None:
        return next((run for run in self.runs if run.user_id == user_id and run.id == run_id), None)

    def list_runs_for_user(self, user_id: str, **kwargs) -> list[AgentRun]:
        workflow_name = kwargs.get("workflow_name")
        return [
            run
            for run in self.runs
            if run.user_id == user_id and (workflow_name is None or run.workflow_name == workflow_name)
        ]

    def set_status(self, run_id: str, status: str, *, metadata_updates: dict | None = None) -> None:
        for index, run in enumerate(self.runs):
            if run.id == run_id:
                metadata = dict(run.metadata)
                metadata.update(metadata_updates or {})
                self.runs[index] = replace(run, status=status, metadata=metadata)
                return
        raise AssertionError(f"missing run: {run_id}")


class _FakeTaskQueue:
    def __init__(self) -> None:
        self.items: list[AgentTask] = []

    def get_by_idempotency_key(self, idempotency_key: str) -> AgentTask | None:
        return next((task for task in self.items if task.idempotency_key == idempotency_key), None)

    def get_by_correlation_id(self, correlation_id: str) -> AgentTask | None:
        return next((task for task in self.items if task.correlation_id == correlation_id), None)

    def enqueue(self, task: TaskEnvelope) -> AgentTask:
        existing = self.get_by_idempotency_key(task.idempotency_key or "")
        if existing is not None:
            return existing
        now = CURRENT_INSTANT
        created = AgentTask(
            id=f"task-{len(self.items) + 1}",
            task_type="agent.workflow",
            status="queued",
            correlation_id=task.correlation_id or "",
            idempotency_key=task.idempotency_key or "",
            payload=dict(task.payload),
            available_at=now,
            claimed_at=None,
            completed_at=None,
            failed_at=None,
            retry_count=0,
            max_attempts=3,
            last_error_type=None,
            last_error_message=None,
            created_at=now,
            updated_at=now,
        )
        self.items.append(created)
        return created

    def enqueue_or_requeue_terminal(self, task: TaskEnvelope) -> AgentTask:
        existing = self.get_by_idempotency_key(task.idempotency_key or "")
        if existing is None:
            return self.enqueue(task)
        if existing.status in {"queued", "processing"}:
            return existing
        requeued = replace(
            existing,
            status="queued",
            correlation_id=task.correlation_id or "",
            payload=dict(task.payload),
            available_at=task.available_at or CURRENT_INSTANT,
            claimed_at=None,
            completed_at=None,
            failed_at=None,
            retry_count=0,
            max_attempts=task.max_attempts,
            last_error_type=None,
            last_error_message=None,
            updated_at=CURRENT_INSTANT,
        )
        self.items[self.items.index(existing)] = requeued
        return requeued

    def set_status(self, idempotency_key: str, status: str) -> None:
        for index, task in enumerate(self.items):
            if task.idempotency_key == idempotency_key:
                self.items[index] = replace(task, status=status)
                return
        raise AssertionError(f"missing task: {idempotency_key}")
