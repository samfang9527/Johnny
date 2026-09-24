from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from src.api.dependencies import build_request_companion_agent
from src.application.async_agent_runs import QueueAgentRunHandler
from src.application.interfaces.task_queue import TaskEnvelope
from src.application.training_plan_regeneration import TrainingPlanRegenerationService
from src.domain.agent_runtime import AgentRun
from src.infrastructure.database.agent_run_repository import SqlAlchemyAgentRunRepository
from src.infrastructure.database.agent_task_queue import SqlAlchemyAgentTaskQueue
from src.infrastructure.database.athlete_race_repository import SqlAlchemyAthleteRaceRepository
from src.infrastructure.database.models import AgentRunModel, AgentTaskModel, AthleteProfileModel, Base, TrainingPlanModel, UserModel
from src.infrastructure.database.session import create_database_engine, create_session_factory, get_database_url
from src.infrastructure.database.training_plan_repository import SqlAlchemyTrainingPlanRepository
from src.infrastructure.llm.settings import load_llm_settings


DEFAULT_CLAIM_TIMEOUT = timedelta(minutes=5)
DEFAULT_RETRY_DELAY = timedelta(seconds=30)
TRAINING_PLAN_DAILY_CHECK_TASK_TYPE = "training-plan.daily-check"
logger = logging.getLogger(__name__)


def schedule_once(session: Session, *, anchor_date: date | None = None) -> int:
    anchor = anchor_date or date.today()
    before = _task_count(session)
    handler = _queue_handler(session)
    for user in _eligible_daily_users(session):
        handler.queue_run(
            user_id=user.id,
            workflow_name="daily_recommendation",
            trigger_type="scheduled",
            idempotency_key=f"daily_recommendation:{user.id}:{anchor.isoformat()}",
            payload={"anchor_date": anchor.isoformat(), "force": False},
        )
    SqlAlchemyAgentTaskQueue(session).enqueue(
        TaskEnvelope(
            task_type=TRAINING_PLAN_DAILY_CHECK_TASK_TYPE,
            payload={"anchor_date": anchor.isoformat()},
            correlation_id=f"training-plan.daily-check:{anchor.isoformat()}",
            idempotency_key=f"training-plan.daily-check:{anchor.isoformat()}",
        )
    )
    return _task_count(session) - before


def schedule_loop(session_factory, *, max_iterations: int | None = None, interval_seconds: float = 60.0) -> int:
    iterations = 0
    enqueued = 0
    while max_iterations is None or iterations < max_iterations:
        with session_factory() as session:
            enqueued += schedule_once(session)
            session.commit()
        iterations += 1
        if max_iterations is not None and iterations >= max_iterations:
            break
        time.sleep(interval_seconds)
    return enqueued


def work_one(session: Session, *, now: datetime | None = None) -> bool:
    queue = SqlAlchemyAgentTaskQueue(session)
    claimed = queue.claim_next(now=now or _utc_now(), claim_timeout=DEFAULT_CLAIM_TIMEOUT)
    if claimed is None:
        return False
    _process_task(session, claimed.id)
    return True


def work_drain(session: Session, *, max_tasks: int | None = None) -> int:
    processed = 0
    while max_tasks is None or processed < max_tasks:
        if not work_one(session):
            break
        processed += 1
    return processed


def work_loop(session_factory, *, idle_timeout_seconds: float | None = None, interval_seconds: float = 1.0) -> int:
    started = time.monotonic()
    processed = 0
    while True:
        with session_factory() as session:
            did_work = work_one(session)
            session.commit()
        if did_work:
            processed += 1
            started = time.monotonic()
            continue
        if idle_timeout_seconds is not None and time.monotonic() - started >= idle_timeout_seconds:
            return processed
        time.sleep(interval_seconds)


def smoke(session: Session, *, user_id: str, timeout_seconds: float = 30.0, workflow: str = "conversation") -> int:
    if workflow == "conversation":
        run = build_request_companion_agent(session).run_conversation(
            user_id=user_id,
            message="How should I adjust today's training?",
        )
        return 0 if run.status == "completed" else 1

    handler = _queue_handler(session)
    if workflow in {"daily_recommendation", "all"}:
        handler.queue_run(
            user_id=user_id,
            workflow_name="daily_recommendation",
            trigger_type="manual",
            idempotency_key=f"smoke:daily:{user_id}:{date.today().isoformat()}",
            payload={"anchor_date": date.today().isoformat(), "force": True},
        )
    if workflow in {"training_plan_generation", "all"}:
        handler.queue_run(
            user_id=user_id,
            workflow_name="training_plan_generation",
            trigger_type="manual",
            idempotency_key=f"smoke:training:{user_id}:{date.today().isoformat()}",
            payload={"plan_type": "base", "starts_on": date.today().isoformat()},
        )
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        processed = work_drain(session)
        if processed == 0:
            return 0
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Johnny async agent scheduler, worker, and smoke commands.")
    parser.add_argument("--database-url", default=None)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("schedule-once")
    schedule_loop_parser = subparsers.add_parser("schedule-loop")
    schedule_loop_parser.add_argument("--max-iterations", type=int, default=None)
    schedule_loop_parser.add_argument("--interval-seconds", type=float, default=60.0)
    subparsers.add_parser("work-one")
    drain_parser = subparsers.add_parser("work-drain")
    drain_parser.add_argument("--max-tasks", type=int, default=None)
    worker_loop_parser = subparsers.add_parser("work-loop")
    worker_loop_parser.add_argument("--idle-timeout-seconds", type=float, default=None)
    worker_loop_parser.add_argument("--interval-seconds", type=float, default=1.0)
    smoke_parser = subparsers.add_parser("smoke")
    smoke_parser.add_argument("--user-id", default="local-user")
    smoke_parser.add_argument("--timeout-seconds", type=float, default=30.0)
    smoke_parser.add_argument("--workflow", default="conversation")
    smoke_parser.add_argument("--live-openai", action="store_true")
    args = parser.parse_args()

    live_openai = getattr(args, "live_openai", False)
    if not live_openai:
        os.environ.pop("LLM_PROVIDER", None)
    elif load_llm_settings() is None:
        print("LLM_PROVIDER=openai, LLM_MODEL, and OPENAI_API_KEY or LLM_API_KEY are required.", file=sys.stderr)
        return 2

    database_url = args.database_url or get_database_url()
    engine = create_database_engine(database_url)
    if database_url.startswith("sqlite"):
        Base.metadata.create_all(engine)
    session_factory = create_session_factory(database_url)

    if args.command == "schedule-loop":
        print(f"enqueued={schedule_loop(session_factory, max_iterations=args.max_iterations, interval_seconds=args.interval_seconds)}")
        return 0
    if args.command == "work-loop":
        print(f"processed={work_loop(session_factory, idle_timeout_seconds=args.idle_timeout_seconds, interval_seconds=args.interval_seconds)}")
        return 0

    with session_factory() as session:
        if args.command == "schedule-once":
            print(f"enqueued={schedule_once(session)}")
            session.commit()
            return 0
        if args.command == "work-one":
            processed = 1 if work_one(session) else 0
            print(f"processed={processed}")
            session.commit()
            return 0
        if args.command == "work-drain":
            print(f"processed={work_drain(session, max_tasks=args.max_tasks)}")
            session.commit()
            return 0
        if args.command == "smoke":
            result = smoke(session, user_id=args.user_id, timeout_seconds=args.timeout_seconds, workflow=args.workflow)
            session.commit()
            return result
    return 2


def _queue_handler(session: Session) -> QueueAgentRunHandler:
    return QueueAgentRunHandler(
        runs=SqlAlchemyAgentRunRepository(session),
        queue=SqlAlchemyAgentTaskQueue(session),
        prompt_version="running-companion-v1",
        provider="local",
        model="deterministic-local-companion",
    )


def _training_plan_regeneration_service(session: Session) -> TrainingPlanRegenerationService:
    athlete_races = SqlAlchemyAthleteRaceRepository(session)
    runs = SqlAlchemyAgentRunRepository(session)
    tasks = SqlAlchemyAgentTaskQueue(session)
    return TrainingPlanRegenerationService(
        profiles=athlete_races,
        race_goals=athlete_races,
        training_plans=SqlAlchemyTrainingPlanRepository(session),
        runs=runs,
        tasks=tasks,
        queue_agent_runs=_queue_handler(session),
    )


def _eligible_daily_users(session: Session) -> list[UserModel]:
    statement = select(UserModel).where(
        UserModel.status == "active",
        exists().where(AthleteProfileModel.user_id == UserModel.id),
        exists().where(
            (TrainingPlanModel.user_id == UserModel.id)
            & (TrainingPlanModel.status == "active")
        ),
    )
    return list(session.scalars(statement))


def _process_task(session: Session, task_id: str) -> None:
    queue = SqlAlchemyAgentTaskQueue(session)
    task = session.get(AgentTaskModel, task_id)
    if task is None:
        return
    if task.task_type == TRAINING_PLAN_DAILY_CHECK_TASK_TYPE:
        _process_training_plan_daily_check(session, task)
        return
    if task.task_type != "agent.workflow":
        queue.fail(
            task_id,
            error_type="UnknownTaskType",
            error_message=f"Unknown task type: {task.task_type}",
            retryable=False,
            now=_utc_now(),
            retry_delay=DEFAULT_RETRY_DELAY,
        )
        return
    payload = task.payload or {}
    run_id = payload.get("run_id")
    workflow_name = payload.get("workflow_name")
    if not run_id or not workflow_name or not isinstance(payload.get("input", {}), dict):
        queue.fail(
            task_id,
            error_type="MalformedTaskPayload",
            error_message="agent.workflow requires run_id, workflow_name, and input payload",
            retryable=False,
            now=_utc_now(),
            retry_delay=DEFAULT_RETRY_DELAY,
        )
        return

    runs = SqlAlchemyAgentRunRepository(session)
    run_model = session.get(AgentRunModel, run_id)
    if run_model is None:
        queue.fail(
            task_id,
            error_type="MalformedTaskPayload",
            error_message="linked agent run not found",
            retryable=False,
            now=_utc_now(),
            retry_delay=DEFAULT_RETRY_DELAY,
        )
        return
    run = runs.get_run_for_user(run_model.user_id, str(run_id))
    if run is None:
        queue.fail(
            task_id,
            error_type="MalformedTaskPayload",
            error_message="linked agent run owner is invalid",
            retryable=False,
            now=_utc_now(),
            retry_delay=DEFAULT_RETRY_DELAY,
        )
        return

    try:
        result = _dispatch_workflow(session, run, workflow_name, payload["input"])
    except Exception as exc:
        queue.fail(
            task_id,
            error_type=exc.__class__.__name__,
            error_message=str(exc),
            retryable=False,
            now=_utc_now(),
            retry_delay=DEFAULT_RETRY_DELAY,
        )
        runs.fail_run(run.fail(error_type=exc.__class__.__name__, error_message=str(exc)))
        return
    if result.status == "completed":
        queue.complete(task_id, now=_utc_now())
    else:
        queue.fail(
            task_id,
            error_type=result.error_type or "WorkflowFailed",
            error_message=result.error_message or "workflow failed",
            retryable=False,
            now=_utc_now(),
            retry_delay=DEFAULT_RETRY_DELAY,
        )


def _process_training_plan_daily_check(session: Session, task: AgentTaskModel) -> None:
    queue = SqlAlchemyAgentTaskQueue(session)
    anchor_date = _daily_check_anchor_date(task.payload or {})
    if anchor_date is None:
        queue.fail(
            task.id,
            error_type="MalformedTaskPayload",
            error_message="training-plan.daily-check requires an ISO anchor_date",
            retryable=False,
            now=_utc_now(),
            retry_delay=DEFAULT_RETRY_DELAY,
        )
        return

    try:
        service = _training_plan_regeneration_service(session)
        candidates = service.find_users_needing_projection(anchor_date)
    except Exception as exc:
        logger.exception("training plan daily check discovery failed", extra={"task_id": task.id})
        queue.fail(
            task.id,
            error_type=exc.__class__.__name__,
            error_message=str(exc),
            retryable=True,
            now=_utc_now(),
            retry_delay=DEFAULT_RETRY_DELAY,
        )
        return

    for candidate in candidates:
        try:
            service.queue_background_generation(candidate)
        except Exception:
            logger.exception(
                "training plan background generation queue failed",
                extra={
                    "task_id": task.id,
                    "user_id": candidate.user_id,
                    "starts_on": candidate.strategy.starts_on.isoformat(),
                },
            )
    queue.complete(task.id, now=_utc_now())


def _daily_check_anchor_date(payload: dict) -> date | None:
    value = payload.get("anchor_date")
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _dispatch_workflow(session: Session, run: AgentRun, workflow_name: str, workflow_input: dict) -> AgentRun:
    agent = build_request_companion_agent(session, provider=run.provider, model=run.model)
    if workflow_name == "daily_recommendation":
        anchor = workflow_input.get("anchor_date")
        anchor_date = date.fromisoformat(anchor) if isinstance(anchor, str) else date.today()
        return agent.run_daily_recommendation(user_id=run.user_id, anchor_date=anchor_date, existing_run=run)
    if workflow_name == "training_plan_generation":
        starts_on = _optional_date(workflow_input.get("starts_on"))
        ends_on = _optional_date(workflow_input.get("ends_on"))
        return agent.run_training_plan_generation(
            user_id=run.user_id,
            race_id=workflow_input.get("race_id"),
            starts_on=starts_on,
            ends_on=ends_on,
            plan_horizon_weeks=workflow_input.get("plan_horizon_weeks"),
            plan_type=workflow_input.get("plan_type") or "race",
            goal_notes=workflow_input.get("goal_notes"),
            existing_run=run,
        )
    raise ValueError(f"Unknown workflow: {workflow_name}")


def _optional_date(value) -> date | None:
    if isinstance(value, date):
        return value
    if isinstance(value, str) and value:
        return date.fromisoformat(value)
    return None


def _task_count(session: Session) -> int:
    return len(session.scalars(select(AgentTaskModel.id)).all())


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


if __name__ == "__main__":
    raise SystemExit(main())
