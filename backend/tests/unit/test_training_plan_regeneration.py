from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timedelta, timezone

from src.api.schemas.training_plan_regeneration import TrainingPlanRegenerationRequest
from src.application.async_agent_runs import QueueAgentRunHandler
from src.application.interfaces.task_queue import AgentTask, TaskEnvelope
from src.application.training_plan_regeneration import TrainingPlanRegenerationService
from src.domain.agent_runtime import AgentRun
from src.domain.athlete_race import AthleteProfile, RaceGoal


TODAY = date(2026, 9, 17)
CURRENT_INSTANT = datetime(2026, 9, 17, 12, tzinfo=timezone.utc)


def test_options_uses_athlete_timezone_for_next_quota_availability() -> None:
    service, runs, _ = _service(profile=_profile(timezone_name="Asia/Taipei"))
    runs.add(_completed_manual_run(quota_day=TODAY, created_plan_id="plan-1"))

    options = service.options("athlete-1", TODAY)

    assert options.quota.available is False
    assert options.quota.quota_day == TODAY
    assert options.quota.next_available_at.isoformat() == "2026-09-18T00:00:00+08:00"


def test_athlete_local_day_drives_quota_races_start_date_and_idempotency_key() -> None:
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
    assert tasks.items[0].idempotency_key == (
        "training_plan_regeneration:athlete-1:2026-09-17:date-boundary"
    )
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


def test_client_request_id_retry_returns_the_same_failed_run() -> None:
    service, runs, tasks = _service()
    request = _request("request-123")

    first = service.start("athlete-1", request, TODAY)
    assert first.run is not None
    tasks.set_status(_idempotency_key("request-123"), "failed")
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
    tasks.set_status(_idempotency_key("request-a"), "failed")
    runs.set_status(terminal.run.run_id, "failed")
    in_flight = service.start("athlete-1", _request("request-b"), TODAY)
    assert in_flight.run is not None

    retried = service.start("athlete-1", retried_request, TODAY)

    assert retried.run is not None
    assert retried.run.run_id == terminal.run.run_id
    assert retried.run.status == "failed"
    assert retried.run.run_id != in_flight.run.run_id
    assert len(tasks.items) == 2


def test_client_request_id_retry_returns_the_same_completed_run_before_quota_blocking() -> None:
    service, runs, tasks = _service()
    request = _request("completed-request")

    first = service.start("athlete-1", request, TODAY)
    assert first.run is not None
    tasks.set_status(_idempotency_key("completed-request"), "completed")
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
    tasks.set_status(_idempotency_key("failed-request"), "failed")
    runs.set_status(first.run.run_id, "failed")
    second = service.start("athlete-1", _request("new-request"), TODAY)

    assert second.run is not None
    assert second.run.run_id != first.run.run_id
    assert [task.idempotency_key for task in tasks.items] == [
        _idempotency_key("failed-request"),
        _idempotency_key("new-request"),
    ]


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


def _service(
    *,
    profile: AthleteProfile | None = None,
    races: list[RaceGoal] | None = None,
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


def _race(race_id: str, race_date: date) -> RaceGoal:
    return RaceGoal.create(
        id=race_id,
        user_id="athlete-1",
        name="Race",
        race_date=race_date,
        distance_meters=21097,
        priority="primary",
    )


def _request(client_request_id: str, *, plan_type: str = "race") -> TrainingPlanRegenerationRequest:
    return TrainingPlanRegenerationRequest(client_request_id=client_request_id, plan_type=plan_type)


def _idempotency_key(client_request_id: str) -> str:
    return f"training_plan_regeneration:athlete-1:2026-09-17:{client_request_id}"


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

    def set_status(self, idempotency_key: str, status: str) -> None:
        for index, task in enumerate(self.items):
            if task.idempotency_key == idempotency_key:
                self.items[index] = replace(task, status=status)
                return
        raise AssertionError(f"missing task: {idempotency_key}")
