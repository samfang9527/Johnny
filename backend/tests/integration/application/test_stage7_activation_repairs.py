from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import sys

import pytest
from sqlalchemy import select

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
import scripts.agent_runtime as worker
from src.api.dependencies import CurrentUser, ensure_current_user
from src.api.regeneration_composition import get_regeneration_options_handler
from src.api.routes.today import get_today
from src.application.agent_tools import TodayWorkoutTool
from src.application.training_analytics import BuildTodayContextHandler
from src.domain.activity_health import CompletedActivity
from src.domain.agent_runtime import AgentRun
from src.domain.athlete_race import RaceGoal
from src.domain.training_plan import TrainingPlan, Workout
from src.infrastructure.database.activity_repository import SqlAlchemyActivityRepository
from src.infrastructure.database.agent_run_repository import SqlAlchemyAgentRunRepository
from src.infrastructure.database.athlete_race_repository import SqlAlchemyAthleteRaceRepository
from src.infrastructure.database.models import AgentTaskModel, Base, TrainingPlanModel
from src.infrastructure.database.training_plan_repository import SqlAlchemyTrainingPlanRepository


TODAY = date(2027, 1, 28)


def _plan(user_id, *, starts_on=TODAY, previous_plan_id=None, workout_day=TODAY):
    return TrainingPlan.create(
        user_id=user_id,
        name="Preserved plan",
        starts_on=starts_on,
        ends_on=starts_on + timedelta(days=27),
        metadata={"previous_plan_id": previous_plan_id, "phase_segments": [{
            "phase": "maintenance", "starts_on": starts_on.isoformat(),
            "ends_on": (starts_on + timedelta(days=27)).isoformat(),
        }]},
        workouts=(Workout.create(
            scheduled_for=workout_day,
            workout_type="easy_run",
            purpose="Aerobic base",
            planned_duration_minutes=30,
            phase="maintenance",
        ),),
    )


def _today(session, user_id, day=TODAY):
    return TodayWorkoutTool(today_context=BuildTodayContextHandler(
        training_data=SqlAlchemyActivityRepository(session),
        training_plans=SqlAlchemyTrainingPlanRepository(session),
    )).run(user_id=user_id, arguments={"anchor_date": day.isoformat()})


def test_today_survives_successive_supersession_and_completion(sqlite_session_factory):
    Base.metadata.create_all(sqlite_session_factory.kw["bind"])
    with sqlite_session_factory() as session:
        ensure_current_user(session, CurrentUser(id="athlete"))
        plans = SqlAlchemyTrainingPlanRepository(session)
        initial = _plan("athlete", starts_on=TODAY - timedelta(days=7))
        historical = Workout.create(
            scheduled_for=TODAY - timedelta(days=1), workout_type="easy_run",
            purpose="Completed aerobic run", planned_duration_minutes=20,
            phase="maintenance", status="completed",
        )
        original = plans.save_plan("athlete", replace(initial, workouts=(*initial.workouts, historical)))
        before = _today(session, "athlete")["scheduled_workouts"]
        assert len(before) == 1 and before[0]["steps"]
        for _ in range(2):
            current = plans.get_current_plan_for_user("athlete")
            plans.create_active_plan("athlete", _plan(
                "athlete", starts_on=TODAY + timedelta(days=1),
                previous_plan_id=current.id, workout_day=TODAY + timedelta(days=2),
            ), replace_all_active=True)
        session.commit()

    with sqlite_session_factory() as session:
        assert _today(session, "athlete")["scheduled_workouts"] == before
        assert get_today(CurrentUser(id="athlete"), session, TODAY).data.scheduled_workouts == before
        assert _today(session, "athlete", TODAY + timedelta(days=1))["scheduled_workouts"] == []
        assert _today(session, "stranger")["scheduled_workouts"] == []
        plans = SqlAlchemyTrainingPlanRepository(session)
        old = plans.get_plan_for_user("athlete", original.id)
        plans.save_plan("athlete", replace(old, workouts=tuple(
            replace(workout, status="completed") if workout.id == before[0]["id"] else workout
            for workout in old.workouts
        )))
        activities = SqlAlchemyActivityRepository(session)
        activities.save_activity("athlete", CompletedActivity.create(
            user_id="athlete", source="manual", sport_type="run",
            started_at=datetime(2027, 1, 28, 7, tzinfo=timezone.utc),
            duration_seconds=1800, distance_meters=5000,
            matched_workout_id=before[0]["id"],
        ))
        session.commit()

    with sqlite_session_factory() as session:
        today = _today(session, "athlete")["scheduled_workouts"]
        assert today[0]["id"] == before[0]["id"]
        assert today[0]["status"] == "completed"
        context = BuildTodayContextHandler(
            training_data=SqlAlchemyActivityRepository(session),
            training_plans=SqlAlchemyTrainingPlanRepository(session),
        ).handle(user_id="athlete", anchor_date=TODAY)
        assert context.recent_activities[0]["matched_workout_id"] == before[0]["id"]
        old = SqlAlchemyTrainingPlanRepository(session).get_plan_for_user("athlete", original.id)
        historical = next(workout for workout in old.workouts if workout.scheduled_for < TODAY)
        assert historical.id in {workout.id for workout in original.workouts}
        assert historical.status == "completed"
        assert len(session.scalars(select(TrainingPlanModel).where(TrainingPlanModel.status == "active")).all()) == 1


@pytest.mark.parametrize("failure", [
    "tool_log", "repair_then_fail", "repair_no_output", "fallback",
    "completion", "worker", "task_completion",
])
def test_worker_commit_rolls_back_failed_activation_and_quota(sqlite_session_factory, monkeypatch, failure):
    Base.metadata.create_all(sqlite_session_factory.kw["bind"])
    with sqlite_session_factory() as session:
        ensure_current_user(session, CurrentUser(id="athlete"))
        original = SqlAlchemyTrainingPlanRepository(session).save_plan("athlete", _plan("athlete"))
        previous_success = SqlAlchemyAgentRunRepository(session).create_run(AgentRun.start(
            user_id="athlete", trigger_type="manual", workflow_name="training_plan_generation",
            prompt_version="v1", metadata={
                "manual_regeneration": True, "quota_day": (TODAY - timedelta(days=1)).isoformat(),
                "created_training_plan_id": original.id,
            },
        ).complete(finished_at=datetime(2027, 1, 27, 12, tzinfo=timezone.utc)))
        queued = worker._queue_handler(session).queue_run(
            user_id="athlete", workflow_name="training_plan_generation", trigger_type="manual",
            idempotency_key="activation-test",
            payload={"plan_type": "maintenance", "starts_on": "2027-01-29",
                     "manual_regeneration": True, "quota_day": TODAY.isoformat()},
        )
        session.commit()

    record_step = SqlAlchemyAgentRunRepository.record_step
    complete_run = SqlAlchemyAgentRunRepository.complete_run
    dispatch = worker._dispatch_workflow
    from src.infrastructure.database.agent_task_queue import SqlAlchemyAgentTaskQueue
    complete_task = SqlAlchemyAgentTaskQueue.complete
    failures = []

    def fail_log(self, step):
        if step.tool_name == "createTrainingPlan":
            failures.append(step.payload["training_plan"]["id"])
            if failure in {"repair_then_fail", "fallback"}:
                raise ValueError("injected post-save validation failure")
            raise RuntimeError("injected post-save log failure")
        return record_step(self, step)

    def fail_completion(self, run):
        if run.status == "completed":
            failures.append(run.metadata["created_training_plan_id"])
            complete_run(self, run)
            if failure == "repair_no_output":
                raise ValueError("injected repairable completion failure")
            raise RuntimeError("injected completion failure")
        return complete_run(self, run)

    def fail_worker(session, run, workflow_name, workflow_input):
        result = dispatch(session, run, workflow_name, workflow_input)
        failures.append(result.metadata["created_training_plan_id"])
        raise RuntimeError("injected dispatch failure after completed runtime")

    def fail_task_completion(self, task_id, *, now):
        complete_task(self, task_id, now=now)
        failures.append(task_id)
        raise RuntimeError("injected task completion failure")

    if failure in {"completion", "repair_no_output"}:
        monkeypatch.setattr(SqlAlchemyAgentRunRepository, "complete_run", fail_completion)
    elif failure == "task_completion":
        monkeypatch.setattr(SqlAlchemyAgentTaskQueue, "complete", fail_task_completion)
    elif failure == "worker":
        monkeypatch.setattr(worker, "_dispatch_workflow", fail_worker)
    else:
        monkeypatch.setattr(SqlAlchemyAgentRunRepository, "record_step", fail_log)
    if failure in {"repair_then_fail", "repair_no_output"}:
        from src.infrastructure.llm.local_gateway import LocalCompanionModelGateway
        complete = LocalCompanionModelGateway.complete
        def fail_retry(self, request):
            if failures:
                if failure == "repair_no_output":
                    from src.domain.agent_runtime import ModelResponse
                    return ModelResponse(content="No replacement plan was created.")
                raise RuntimeError("injected retry model failure")
            return complete(self, request)
        monkeypatch.setattr(LocalCompanionModelGateway, "complete", fail_retry)

    with sqlite_session_factory() as session:
        assert worker.work_one(session)
        session.commit()

    with sqlite_session_factory() as session:
        assert failures, "failure must occur after real persistence"
        plans = SqlAlchemyTrainingPlanRepository(session).list_plans_for_user("athlete")
        assert [(plan.id, plan.status) for plan in plans] == [(original.id, "active")]
        assert plans[0] == original
        run = SqlAlchemyAgentRunRepository(session).get_run_for_user("athlete", queued.run.id)
        assert run.status == "failed"
        assert "created_training_plan_id" not in run.metadata
        previous = SqlAlchemyAgentRunRepository(session).get_run_for_user("athlete", previous_success.id)
        assert previous.status == "completed"
        assert previous.metadata == previous_success.metadata
        assert get_regeneration_options_handler(session).handle(user_id="athlete", today=TODAY - timedelta(days=1)).quota.used == 1
        assert session.get(AgentTaskModel, queued.task.id).status == "failed"
        options = get_regeneration_options_handler(session).handle(user_id="athlete", today=TODAY)
        assert options.quota.used == 0
        assert options.quota.available


@pytest.mark.parametrize("predecessor", ["missing", "foreign", "cycle", "draft", "recovery_window"])
def test_today_does_not_resurrect_unrelated_or_expired_predecessors(sqlite_session_factory, predecessor):
    Base.metadata.create_all(sqlite_session_factory.kw["bind"])
    with sqlite_session_factory() as session:
        ensure_current_user(session, CurrentUser(id="athlete"))
        ensure_current_user(session, CurrentUser(id="other"))
        plans = SqlAlchemyTrainingPlanRepository(session)
        old = _plan("other" if predecessor == "foreign" else "athlete")
        if predecessor == "draft":
            old = replace(old, status="draft")
        if predecessor == "recovery_window":
            old = replace(old, starts_on=TODAY - timedelta(days=28), ends_on=TODAY - timedelta(days=1), workouts=())
        old = plans.save_plan(old.user_id, old)
        current = plans.create_active_plan("athlete", _plan(
            "athlete", starts_on=TODAY + timedelta(days=1), workout_day=TODAY + timedelta(days=2),
            previous_plan_id="missing" if predecessor == "missing" else old.id,
        ), replace_all_active=True)
        if predecessor == "cycle":
            plans.save_plan("athlete", replace(current, metadata={**current.metadata, "previous_plan_id": current.id}))
        session.commit()
    with sqlite_session_factory() as session:
        assert _today(session, "athlete")["scheduled_workouts"] == []


def test_api_service_defaults_to_current_future_race_then_falls_back(sqlite_session_factory):
    Base.metadata.create_all(sqlite_session_factory.kw["bind"])
    with sqlite_session_factory() as session:
        ensure_current_user(session, CurrentUser(id="athlete"))
        races = SqlAlchemyAthleteRaceRepository(session)
        secondary = races.create_race_goal("athlete", RaceGoal.create(
            user_id="athlete", name="Current strategy", race_date=TODAY + timedelta(days=20),
            distance_meters=10000, priority="secondary",
        ))
        primary = races.create_race_goal("athlete", RaceGoal.create(
            user_id="athlete", name="New primary", race_date=TODAY + timedelta(days=30),
            distance_meters=21097, priority="primary",
        ))
        plans = SqlAlchemyTrainingPlanRepository(session)
        plan = plans.save_plan("athlete", replace(_plan("athlete"), race_id=secondary.id))
        assert get_regeneration_options_handler(session).handle(user_id="athlete", today=TODAY).default_strategy.race_id == secondary.id
        assert get_regeneration_options_handler(session).handle(user_id="athlete", today=secondary.race_date).default_strategy.race_id == primary.id
        plans.save_plan("athlete", replace(plan, race_id=None))
        assert get_regeneration_options_handler(session).handle(user_id="athlete", today=TODAY).default_strategy.race_id == primary.id


def test_same_run_repair_rolls_back_first_save_before_success(sqlite_session_factory, monkeypatch):
    monkeypatch.setattr("src.domain.agent_runtime._utc_now", lambda: datetime(2027, 1, 28, 12, tzinfo=timezone.utc))
    Base.metadata.create_all(sqlite_session_factory.kw["bind"])
    with sqlite_session_factory() as session:
        ensure_current_user(session, CurrentUser(id="athlete"))
        original = SqlAlchemyTrainingPlanRepository(session).save_plan("athlete", _plan("athlete"))
        queued = worker._queue_handler(session).queue_run(
            user_id="athlete", workflow_name="training_plan_generation", trigger_type="manual",
            idempotency_key="repair-success",
            payload={"plan_type": "maintenance", "starts_on": "2027-01-29",
                     "manual_regeneration": True, "quota_day": TODAY.isoformat()},
        )
        session.commit()
    record = SqlAlchemyAgentRunRepository.record_step
    rejected_ids = []
    def fail_first_save_log(self, step):
        if step.tool_name == "createTrainingPlan" and not rejected_ids:
            rejected_ids.append(step.payload["training_plan"]["id"])
            raise ValueError("repairable failure after saving")
        return record(self, step)
    monkeypatch.setattr(SqlAlchemyAgentRunRepository, "record_step", fail_first_save_log)
    with sqlite_session_factory() as session:
        assert worker.work_one(session)
        session.commit()
    with sqlite_session_factory() as session:
        plans = SqlAlchemyTrainingPlanRepository(session).list_plans_for_user("athlete")
        assert len(plans) == 2
        assert not any(plan.id in rejected_ids for plan in plans)
        active = next(plan for plan in plans if plan.status == "active")
        assert active.metadata["previous_plan_id"] == original.id
        assert next(plan for plan in plans if plan.id == original.id).status == "superseded"
        run = SqlAlchemyAgentRunRepository(session).get_run_for_user("athlete", queued.run.id)
        assert run.status == "completed"
        assert run.metadata["created_training_plan_id"] == active.id
        assert get_regeneration_options_handler(session).handle(user_id="athlete", today=TODAY).quota.used == 1
        assert _today(session, "athlete")["scheduled_workouts"][0]["id"] == original.workouts[0].id
