from __future__ import annotations

import argparse
from dataclasses import replace
import logging
import os
import signal
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Callable
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from sqlalchemy import exists, select
from sqlalchemy.orm import Session, sessionmaker

from src.api.dependencies import build_request_companion_agent
from src.application.async_agent_runs import QueueAgentRunHandler
from src.application.task_contracts import SUPPORTED_TASK_CONTRACTS
from src.application.coaching_analysis_generation import (
    PROMPT_VERSIONS, coaching_analysis_v2_enabled, generate_coaching_analysis,
)
from src.application.activity_detail_sync import (
    ActivityDetailDeferred, ActivityDetailRetry, ActivityDetailSyncService,
    FETCH_TASK as ACTIVITY_DETAIL_FETCH_TASK, FINALIZE_TASK as ACTIVITY_DETAIL_FINALIZE_TASK,
    RECHECK_TASK as ACTIVITY_DETAIL_RECHECK_TASK,
)
from src.application.daily_advice_generation import GenerateDailyAdviceHandler
from src.application.training_review_generation import GenerateTrainingReviewHandler
from src.application.workout_advice_generation import GenerateWorkoutAdviceHandler
from src.domain.workout_advice import WorkoutAdviceConstraints
from src.domain.training_review import review_period
from src.application.daily_advice_sync import activity_sync_usable, recovery_data_limited
from src.application.training_analytics import BuildTodayContextHandler
from src.application.training_analytics import resolve_plan_for_date
from src.application.integrations import GarminInitialSyncCommand, GarminInitialSyncHandler
from src.application.interfaces.task_queue import TaskEnvelope
from src.application.training_plan_regeneration import TrainingPlanRegenerationService
from src.domain.agent_runtime import AgentRun
from src.domain.daily_advice import RefreshVersion
from src.domain.integrations_notifications import SyncAlreadyRunningError
from src.infrastructure.database.activity_repository import SqlAlchemyActivityRepository
from src.infrastructure.database.agent_run_repository import SqlAlchemyAgentRunRepository
from src.infrastructure.database.agent_task_queue import SqlAlchemyAgentTaskQueue
from src.infrastructure.database.athlete_race_repository import SqlAlchemyAthleteRaceRepository
from src.infrastructure.database.daily_advice_repository import SqlAlchemyDailyAdviceRepository
from src.infrastructure.database.coaching_repository import SqlAlchemyCoachingRepository
from src.infrastructure.database.integration_repository import SqlAlchemyIntegrationRepository
from src.infrastructure.database.outbox_repository import SqlAlchemyOutboxRepository
from src.infrastructure.database.models import ActivityModel, AgentRunModel, AgentTaskModel, AthleteProfileModel, Base, TrainingPlanModel, TrainingReviewModel, WorkoutAdviceModel, UserModel
from src.infrastructure.database.session import create_database_engine, create_session_factory, get_database_url
from src.infrastructure.database.training_plan_repository import SqlAlchemyTrainingPlanRepository
from src.infrastructure.llm.local_gateway import LocalCompanionModelGateway
from src.infrastructure.llm.openai_gateway import OpenAIModelGateway
from src.infrastructure.llm.settings import LlmSettingsError, load_llm_settings, load_openai_settings_for_queued_model, resolve_queued_daily_advice_provider, resolve_queued_training_plan_provider
from src.infrastructure.integrations.garminconnect_adapter import GarminConnectResourceAdapter
from src.infrastructure.integrations.garmin_normalizer import normalize_garmin_activity, normalize_garmin_daily_health, normalize_garmin_training_evidence
from src.infrastructure.security.integration_credentials import load_garmin_credential_cipher
from src.infrastructure.logging.logger_config import setup_logging


DEFAULT_CLAIM_TIMEOUT = timedelta(minutes=5)
DEFAULT_RETRY_DELAY = timedelta(seconds=30)
TRAINING_PLAN_DAILY_CHECK_TASK_TYPE = "training-plan.daily-check"
DAILY_ADVICE_SYNC_TASK_TYPE = "daily_advice.sync"
COACHING_SYNC_TASK_TYPE = "coaching.sync"
logger = logging.getLogger(__name__)


def schedule_once(session: Session, *, now: datetime | None = None) -> int:
    instant = now or _utc_now()
    if instant.tzinfo is None or instant.utcoffset() is None:
        raise ValueError("schedule_once requires a timezone-aware instant")
    instant = instant.astimezone(timezone.utc)
    started = time.monotonic()
    logger.info("agent scheduler started instant=%s", instant.isoformat())
    before = _task_count(session)
    handler = _review_queue_handler(session)
    coaching = SqlAlchemyCoachingRepository(session)
    from src.application.coaching_refresh import CoachingRefreshService
    refresh = CoachingRefreshService(session)
    for user, timezone_name in _eligible_daily_users(session):
        try:
            local_date = _due_local_date(instant, timezone_name)
        except ZoneInfoNotFoundError:
            logger.warning("daily advice schedule skipped invalid timezone user_id=%s timezone=%s", user.id, timezone_name)
            continue
        if local_date is None:
            continue
        key = f"daily_review:{user.id}:{local_date.isoformat()}"
        recovered_run_id = refresh.recover_failed_review(
            user_id=user.id, publication_date=local_date, timezone_name=timezone_name)
        if recovered_run_id:
            logger.warning("requeueing review rejected by old worker user_id=%s date=%s",
                           user.id, local_date)
            continue
        queued = handler.queue_run(
            user_id=user.id,
            workflow_name="daily_review",
            trigger_type="scheduled",
            idempotency_key=key,
            payload={"publication_date": local_date.isoformat(), "timezone_name": timezone_name},
            task_type=COACHING_SYNC_TASK_TYPE,
            reuse_terminal=True,
        )
        logger.info(
            "agent scheduler review task task_id=%s run_id=%s user_id=%s date=%s status=%s",
            queued.task.id, queued.run.id, user.id, local_date, queued.task.status,
        )
        if queued.run.status == "queued":
            slot = coaching.get_review_slot(user.id, local_date)
            if slot is None or slot["reserved_run_id"] != queued.run.id:
                coaching.reserve_review(user.id, local_date, timezone_name, queued.run.id)
    anchor = instant.date()
    daily_check = SqlAlchemyAgentTaskQueue(session).enqueue(
        TaskEnvelope(
            task_type=TRAINING_PLAN_DAILY_CHECK_TASK_TYPE,
            payload={"anchor_date": anchor.isoformat()},
            correlation_id=f"training-plan.daily-check:{anchor.isoformat()}",
            idempotency_key=f"training-plan.daily-check:{anchor.isoformat()}",
        )
    )
    enqueued = _task_count(session) - before
    logger.info(
        "agent scheduler finished instant=%s daily_check_task_id=%s daily_check_status=%s enqueued=%s duration_ms=%s",
        instant.isoformat(), daily_check.id, daily_check.status, enqueued,
        round((time.monotonic() - started) * 1000),
    )
    return enqueued


def _due_local_date(now: datetime, timezone_name: str) -> date | None:
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("daily advice schedule requires a timezone-aware instant")
    local = now.astimezone(ZoneInfo(timezone_name))
    return local.date() if local.hour >= 4 else None


def schedule_loop(session_factory, *, max_iterations: int | None = None, interval_seconds: float = 60.0, should_stop: Callable[[], bool] = lambda: False) -> int:
    iterations = 0
    enqueued = 0
    while (max_iterations is None or iterations < max_iterations) and not should_stop():
        with session_factory() as session:
            enqueued += schedule_once(session)
            session.commit()
        iterations += 1
        if max_iterations is not None and iterations >= max_iterations:
            break
        time.sleep(interval_seconds)
    return enqueued


def work_one(session: Session, *, now: datetime | None = None) -> bool:
    instant = now or _utc_now()
    queue = SqlAlchemyAgentTaskQueue(session)
    claimed = queue.claim_next(now=instant, claim_timeout=DEFAULT_CLAIM_TIMEOUT,
                               supported_contracts=SUPPORTED_TASK_CONTRACTS)
    if claimed is None:
        return False
    started = time.monotonic()
    run_id = claimed.payload.get("run_id") if isinstance(claimed.payload, dict) else None
    logger.info(
        "worker task claimed task_id=%s task_type=%s run_id=%s correlation_id=%s retry_count=%s",
        claimed.id, claimed.task_type, run_id, claimed.correlation_id, claimed.retry_count,
    )
    try:
        if claimed.task_type in {ACTIVITY_DETAIL_FETCH_TASK, ACTIVITY_DETAIL_FINALIZE_TASK,
                                 ACTIVITY_DETAIL_RECHECK_TASK}:
            session.commit()  # Persist the task claim before the service's independent transactions.
            _process_activity_detail_task(session, claimed, now=instant)
            session.commit()
        else:
            _process_task(session, claimed.id)
        if claimed.task_type in {DAILY_ADVICE_SYNC_TASK_TYPE, COACHING_SYNC_TASK_TYPE}:
            # Imported activities and the generation task become visible together.
            session.commit()
    except Exception as exc:
        logger.error(
            "worker task raised task_id=%s task_type=%s run_id=%s error_type=%s duration_ms=%s",
            claimed.id, claimed.task_type, run_id, type(exc).__name__,
            round((time.monotonic() - started) * 1000),
        )
        raise
    task = session.get(AgentTaskModel, claimed.id)
    logger.info(
        "worker task finished task_id=%s task_type=%s run_id=%s status=%s error_type=%s duration_ms=%s",
        claimed.id, claimed.task_type, run_id, task.status if task else "missing",
        task.last_error_type if task else None,
        round((time.monotonic() - started) * 1000),
    )
    return True


def _build_detail_service(session: Session) -> ActivityDetailSyncService:
    factory = sessionmaker(bind=session.get_bind(), expire_on_commit=False)
    def adapter_factory(provider_session: Session):
        return GarminConnectResourceAdapter(
            credentials=SqlAlchemyIntegrationRepository(provider_session),
            cipher=load_garmin_credential_cipher())
    return ActivityDetailSyncService(factory, adapter_factory)


def _start_coaching_detail_batch(session: Session, user_id: str, connection_id: str,
                                 summary, timezone_name: str, source_sync_run_id: str) -> str | None:
    if os.getenv('JOHNNY_ACTIVITY_DETAILS_ENABLED', '').lower() not in {'1', 'true', 'yes'}:
        return None
    raw_dates = summary.stored_dates.get('activities') or ()
    if not raw_dates:
        return None
    days = {date.fromisoformat(value) for value in raw_dates}
    zone = ZoneInfo(timezone_name)
    recordings = session.scalars(select(ActivityModel).where(
        ActivityModel.user_id == user_id,
        ActivityModel.provider_connection_id == connection_id,
        ActivityModel.provider_activity_id.is_not(None))).all()
    ids = tuple(sorted(activity.id for activity in recordings
        if (activity.started_at.replace(tzinfo=timezone.utc)
            if activity.started_at.tzinfo is None else activity.started_at).astimezone(zone).date() in days))
    if not ids:
        return None
    session.commit()  # Detail batch uses an independent session; commit imported summaries first.
    try:
        return _build_detail_service(session).start_batch(user_id=user_id,
            activity_ids=ids, source_sync_run_id=source_sync_run_id, now=_utc_now())
    except ValueError:
        logger.warning('coaching detail batch unavailable user_id=%s sync_run_id=%s',
                       user_id, source_sync_run_id)
        return None


def _process_activity_detail_task(session: Session, task, *, now: datetime) -> None:
    queue = SqlAlchemyAgentTaskQueue(session)
    if os.getenv('JOHNNY_ACTIVITY_DETAILS_ENABLED', '').lower() not in {'1', 'true', 'yes'}:
        queue.defer(task.id, now=now, delay=timedelta(hours=1))
        return
    service = _build_detail_service(session)
    payload = task.payload or {}
    try:
        if task.task_type == ACTIVITY_DETAIL_FETCH_TASK and isinstance(payload.get('fetch_id'), str):
            service.process_resource(fetch_id=payload['fetch_id'], now=now)
        elif task.task_type == ACTIVITY_DETAIL_FINALIZE_TASK and isinstance(payload.get('batch_id'), str):
            changed = service.finalize_batch(batch_id=payload['batch_id'], now=now)
            session.expire_all()  # The detail service committed in its own session.
            finalizer = session.scalar(select(AgentTaskModel).where(
                AgentTaskModel.idempotency_key == f'{ACTIVITY_DETAIL_FINALIZE_TASK}:{payload["batch_id"]}'))
            persisted = finalizer.payload or {} if finalizer else {}
            changed = changed or tuple(persisted.get('changed_activity_ids') or ())
            from src.application.coaching_refresh import CoachingRefreshService
            CoachingRefreshService(session).complete_detail_batch(
                batch_id=payload['batch_id'], changed_activity_ids=changed, now=now)
            continuation = (finalizer.payload or {}).get('coaching_continuation') if finalizer else None
            if continuation:
                runs = SqlAlchemyAgentRunRepository(session)
                run = runs.get_run_for_user(continuation['user_id'], continuation['run_id'])
                if run is not None and run.status == 'queued':
                    _enqueue_coaching_generation(session, run=run,
                        workflow_input=continuation['workflow_input'],
                        source_sync_run_id=continuation['source_sync_run_id'])
        elif (task.task_type == ACTIVITY_DETAIL_RECHECK_TASK
              and all(isinstance(payload.get(key), str) for key in
                      ('user_id', 'activity_id', 'resource', 'origin_batch_id'))
              and payload.get('ordinal') in (1, 2)):
            service.run_recheck(user_id=payload['user_id'], activity_id=payload['activity_id'],
                                resource=payload['resource'], origin_batch_id=payload['origin_batch_id'],
                                ordinal=payload['ordinal'], now=now)
        else:
            queue.fail(task.id, error_type='MalformedTaskPayload',
                       error_message='activity detail task has an invalid payload',
                       retryable=False, now=now, retry_delay=DEFAULT_RETRY_DELAY)
            return
    except ActivityDetailDeferred as exc:
        queue.defer(task.id, now=now, delay=exc.delay)
        return
    except ActivityDetailRetry as exc:
        queue.fail(task.id, error_type=exc.category, error_message=exc.category,
                   retryable=True, now=now, retry_delay=exc.delay)
        return
    queue.complete(task.id, now=now)


def work_drain(session: Session, *, max_tasks: int | None = None) -> int:
    processed = 0
    while max_tasks is None or processed < max_tasks:
        if not work_one(session):
            break
        processed += 1
    return processed


def work_loop(session_factory, *, idle_timeout_seconds: float | None = None, interval_seconds: float = 1.0, should_stop: Callable[[], bool] = lambda: False) -> int:
    started = time.monotonic()
    processed = 0
    while True:
        if should_stop():
            return processed
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


def smoke(
    session: Session, *, user_id: str, timeout_seconds: float = 30.0,
    workflow: str = "daily_review", live_openai: bool = False,
) -> int:
    if workflow == "conversation":
        run = build_request_companion_agent(session, provider=None if live_openai else "local").run_conversation(
            user_id=user_id,
            message="How should I adjust today's training?",
        )
        return 0 if run.status == "completed" else 1

    profile = session.scalar(select(AthleteProfileModel).where(AthleteProfileModel.user_id == user_id))
    timezone_name = profile.timezone if profile else "UTC"
    local_date = _utc_now().astimezone(ZoneInfo(timezone_name)).date()
    if workflow in {"daily_review", "all"}:
        queued = _review_queue_handler(session).queue_run(
            user_id=user_id, workflow_name="daily_review", trigger_type="manual",
            idempotency_key=f"smoke:review:{user_id}:{local_date.isoformat()}",
            payload={"publication_date": local_date.isoformat(), "timezone_name": timezone_name},
            task_type=COACHING_SYNC_TASK_TYPE,
        )
        SqlAlchemyCoachingRepository(session).reserve_review(
            user_id, local_date, timezone_name, queued.run.id)
    if workflow in {"workout_advice", "all"}:
        plan = SqlAlchemyTrainingPlanRepository(session).get_plan_for_date_raw(user_id, local_date)
        workouts = tuple(item for item in plan.workouts if item.scheduled_for == local_date) if plan else ()
        workout_id = workouts[0].id if workouts else None
        queued = _queue_handler(session).queue_run(
            user_id=user_id, workflow_name="workout_advice", trigger_type="manual",
            idempotency_key=f"smoke:advice:{user_id}:{local_date.isoformat()}",
            payload={"advice_date": local_date.isoformat(), "timezone_name": timezone_name,
                     "workout_id": workout_id, "constraints": {
                         "available_minutes": None, "feeling": "usual", "cannot_train_today": False,
                     }}, task_type=COACHING_SYNC_TASK_TYPE,
        )
        SqlAlchemyCoachingRepository(session).reserve_advice(
            user_id, local_date, workout_id or "no-workout", queued.run.id,
            {"available_minutes": None, "feeling": "usual", "cannot_train_today": False},
        )
    if workflow in {"training_plan_generation", "all"}:
        (_training_plan_queue_handler(session) if live_openai else _queue_handler(session)).queue_run(
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
    smoke_parser.add_argument("--workflow", default="daily_review")
    smoke_parser.add_argument("--live-openai", action="store_true")
    args = parser.parse_args()
    setup_logging()
    logger.info("agent runtime command started command=%s", args.command)

    live_openai = getattr(args, "live_openai", False)
    if live_openai and load_llm_settings() is None:
        print("LLM_PROVIDER=openai, LLM_MODEL, and OPENAI_API_KEY or LLM_API_KEY are required.", file=sys.stderr)
        return 2

    database_url = args.database_url or get_database_url()
    engine = create_database_engine(database_url)
    if database_url.startswith("sqlite"):
        Base.metadata.create_all(engine)
    session_factory = create_session_factory(database_url)

    stop_requested = False
    if args.command in {"schedule-loop", "work-loop"}:
        def request_stop(_signum: int, _frame: object) -> None:
            nonlocal stop_requested
            stop_requested = True
            logger.info("agent runtime shutdown requested command=%s", args.command)

        signal.signal(signal.SIGTERM, request_stop)
        signal.signal(signal.SIGINT, request_stop)

    if args.command == "schedule-loop":
        print(f"enqueued={schedule_loop(session_factory, max_iterations=args.max_iterations, interval_seconds=args.interval_seconds, should_stop=lambda: stop_requested)}")
        return 0
    if args.command == "work-loop":
        print(f"processed={work_loop(session_factory, idle_timeout_seconds=args.idle_timeout_seconds, interval_seconds=args.interval_seconds, should_stop=lambda: stop_requested)}")
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
            result = smoke(
                session, user_id=args.user_id, timeout_seconds=args.timeout_seconds,
                workflow=args.workflow, live_openai=live_openai,
            )
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


def _review_queue_handler(session: Session) -> QueueAgentRunHandler:
    provider, model = resolve_queued_training_plan_provider()
    return QueueAgentRunHandler(
        runs=SqlAlchemyAgentRunRepository(session),
        queue=SqlAlchemyAgentTaskQueue(session),
        prompt_version=(PROMPT_VERSIONS['daily_review'] if coaching_analysis_v2_enabled()
                        else "johnny-review-analysis-v1"),
        provider=provider, model=model,
    )


class _UnavailableCoachingGateway:
    def complete(self, request):
        raise RuntimeError('queued coaching model credentials unavailable')


def _queued_coaching_gateway(run: AgentRun):
    if run.provider != 'openai':
        return None
    try:
        settings = load_openai_settings_for_queued_model(run.model or '')
        return OpenAIModelGateway(model=run.model or '', api_key=settings.api_key)
    except LlmSettingsError:
        return _UnavailableCoachingGateway()


def _training_plan_queue_handler(session: Session) -> QueueAgentRunHandler:
    provider, model = resolve_queued_training_plan_provider()
    return QueueAgentRunHandler(
        runs=SqlAlchemyAgentRunRepository(session),
        queue=SqlAlchemyAgentTaskQueue(session),
        prompt_version="running-companion-v1",
        provider=provider,
        model=model,
    )


def _daily_advice_queue_handler(session: Session) -> QueueAgentRunHandler:
    provider, model = resolve_queued_daily_advice_provider()
    return QueueAgentRunHandler(
        runs=SqlAlchemyAgentRunRepository(session),
        queue=SqlAlchemyAgentTaskQueue(session),
        prompt_version="running-companion-v1", provider=provider, model=model,
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
        queue_agent_runs=_training_plan_queue_handler(session),
        current_instant=_utc_now,
    )


def _eligible_daily_users(session: Session) -> list[tuple[UserModel, str]]:
    statement = select(UserModel, AthleteProfileModel.timezone).join(
        AthleteProfileModel, AthleteProfileModel.user_id == UserModel.id,
    ).where(UserModel.status == "active")
    return list(session.execute(statement).all())


def _process_task(session: Session, task_id: str) -> None:
    queue = SqlAlchemyAgentTaskQueue(session)
    task = session.get(AgentTaskModel, task_id)
    if task is None:
        return
    if task.task_type == DAILY_ADVICE_SYNC_TASK_TYPE or (
        task.task_type == "agent.workflow"
        and (task.payload or {}).get("workflow_name") == "daily_recommendation"
    ):
        _retire_legacy_daily_advice_task(session, task)
        return
    if task.task_type == TRAINING_PLAN_DAILY_CHECK_TASK_TYPE:
        _process_training_plan_daily_check(session, task)
        return
    if task.task_type == COACHING_SYNC_TASK_TYPE:
        _process_coaching_sync(session, task)
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

    workflow_input = dict(payload["input"])
    started = time.monotonic()
    logger.info(
        "worker workflow started run_id=%s workflow=%s provider=%s model=%s task_id=%s",
        run_id, workflow_name, run.provider, run.model, task_id,
    )
    try:
        with session.begin_nested():
            run, workflow_input = _refresh_scheduled_training_plan_context(
                session,
                runs=runs,
                run=run,
                workflow_name=workflow_name,
                workflow_input=workflow_input,
            )
            if workflow_input != payload["input"]:
                task.payload = {**payload, "input": dict(workflow_input)}
                session.flush()
            result = _dispatch_workflow(session, run, workflow_name, workflow_input)
            if result.status == "completed":
                queue.complete(task_id, now=_utc_now())
    except Exception as exc:
        logger.error(
            "worker workflow raised run_id=%s workflow=%s error_type=%s task_id=%s duration_ms=%s",
            run_id, workflow_name, type(exc).__name__, task_id,
            round((time.monotonic() - started) * 1000),
        )
        queue.fail(
            task_id,
            error_type=exc.__class__.__name__,
            error_message=str(exc),
            retryable=False,
            now=_utc_now(),
            retry_delay=DEFAULT_RETRY_DELAY,
        )
        runs.fail_run(run.fail(error_type=exc.__class__.__name__, error_message=str(exc)))
        request_id = workflow_input.get('generation_request_id')
        if workflow_name == 'daily_review' and request_id:
            from src.application.coaching_refresh import CoachingRefreshService
            refresh = CoachingRefreshService(session)
            if 'inputs changed' in str(exc):
                refresh.reconcile_changed_review_request(request_id)
            else:
                refresh.fail_review_request(request_id)
        return
    logger.info(
        "worker workflow finished run_id=%s workflow=%s status=%s error_type=%s task_id=%s duration_ms=%s",
        run_id, workflow_name, result.status, result.error_type, task_id,
        round((time.monotonic() - started) * 1000),
    )
    if result.status != "completed":
        queue.fail(
            task_id,
            error_type=result.error_type or "WorkflowFailed",
            error_message=result.error_message or "workflow failed",
            retryable=False,
            now=_utc_now(),
            retry_delay=DEFAULT_RETRY_DELAY,
        )


def _retire_legacy_daily_advice_task(session: Session, task: AgentTaskModel) -> None:
    """Terminally retire pre-cutover work without publishing an old combined advice card."""
    reason = "LegacyDailyAdviceRetired"
    SqlAlchemyAgentTaskQueue(session).fail(
        task.id, error_type=reason,
        error_message="Legacy Daily Advice has been replaced by Johnny review and workout advice",
        retryable=False, now=_utc_now(), retry_delay=DEFAULT_RETRY_DELAY,
    )
    run_id = (task.payload or {}).get("run_id")
    run_model = session.get(AgentRunModel, run_id) if run_id else None
    if run_model is not None and run_model.status not in {"completed", "failed"}:
        runs = SqlAlchemyAgentRunRepository(session)
        run = runs.get_run_for_user(run_model.user_id, run_id)
        if run is not None:
            runs.fail_run(run.fail(
                error_type=reason,
                error_message="Legacy Daily Advice was retired at the coaching cutover",
            ))


def _enqueue_daily_advice_generation(
    session: Session, *, run: AgentRun, anchor_date: date,
    source_sync_run_id: str | None, limited_recovery: bool,
    observed_at: datetime,
) -> None:
    SqlAlchemyAgentTaskQueue(session).enqueue(TaskEnvelope(
        task_type="agent.workflow",
        payload={
            "run_id": run.id, "workflow_name": "daily_recommendation",
            "input": {
                "anchor_date": anchor_date.isoformat(),
                "source_sync_run_id": source_sync_run_id,
                "limited_recovery": limited_recovery,
                "refresh_observed_at": observed_at.isoformat(),
            },
        },
        correlation_id=run.id,
        idempotency_key=f"daily_advice.generate:{run.id}",
    ))


def _enqueue_coaching_generation(session: Session, *, run: AgentRun,
                                 workflow_input: dict, source_sync_run_id: str | None) -> None:
    workflow_name = run.workflow_name
    SqlAlchemyAgentTaskQueue(session).enqueue(TaskEnvelope(
        task_type="agent.workflow",
        payload={"run_id": run.id, "workflow_name": workflow_name,
                 "input": {**workflow_input, "source_sync_run_id": source_sync_run_id}},
        correlation_id=run.id,
        idempotency_key=f"{workflow_name}.generate:{run.id}",
    ))


def _process_coaching_sync(session: Session, task: AgentTaskModel) -> None:
    queue = SqlAlchemyAgentTaskQueue(session)
    payload = task.payload or {}
    run_id = payload.get("run_id")
    workflow_input = payload.get("input") or {}
    run_model = session.get(AgentRunModel, run_id) if run_id else None
    if run_model is None or payload.get("workflow_name") not in {"daily_review", "workout_advice"}:
        queue.fail(task.id, error_type="MalformedTaskPayload", error_message="coaching sync requires a linked review/advice run",
                   retryable=False, now=_utc_now(), retry_delay=DEFAULT_RETRY_DELAY)
        return
    runs = SqlAlchemyAgentRunRepository(session)
    run = runs.get_run_for_user(run_model.user_id, run_id)
    if run is None:
        queue.fail(task.id, error_type="MalformedTaskPayload", error_message="coaching run owner mismatch",
                   retryable=False, now=_utc_now(), retry_delay=DEFAULT_RETRY_DELAY)
        return
    integrations = SqlAlchemyIntegrationRepository(session)
    connections = [item for item in integrations.list_active_connections_for_user(run.user_id)
                   if item.provider == "garmin_connect"]
    if not connections:
        _enqueue_coaching_generation(session, run=run,
            workflow_input={**workflow_input, "manual_only": True}, source_sync_run_id=None)
        queue.complete(task.id, now=_utc_now())
        return
    connection = connections[0]
    if connection.sync_status == "running":
        _defer_daily_advice_sync(session, task.id)
        return
    if connection.credential_status == "requires_reauth":
        _fail_coaching_sync(session, task, run, "GarminRequiresReauth")
        return
    try:
        try:
            sync_run = integrations.start_sync_run(connection.id)
        except SyncAlreadyRunningError:
            _defer_daily_advice_sync(session, task.id)
            return
        session.commit()  # Publish the provider lease before network I/O.
        summary = GarminInitialSyncHandler(
            normalize_training_evidence=normalize_garmin_training_evidence,
            integrations=integrations, activities=SqlAlchemyActivityRepository(session),
            outbox=SqlAlchemyOutboxRepository(session), garmin=_build_garmin_sync_adapter(session, integrations),
            athlete_profiles=SqlAlchemyAthleteRaceRepository(session),
            normalize_activity=lambda user_id, connection_id, activity: normalize_garmin_activity(
                user_id=user_id, provider_connection_id=connection_id, payload=activity),
            normalize_health=lambda user_id, health: normalize_garmin_daily_health(
                user_id=user_id, payload=health),
        ).handle(GarminInitialSyncCommand(
            user_id=run.user_id, connection_id=connection.id, as_of=_utc_now(), sync_run_id=sync_run.id,
        ))
        saved_sync = integrations.get_latest_sync_run_for_connection(connection.id)
        refreshed = integrations.get_connection_for_user(run.user_id, connection.id)
        if saved_sync is None or refreshed is None or not activity_sync_usable(
            summary, saved_sync.status, refreshed.credential_status,
        ):
            _fail_coaching_sync(session, task, run, "ActivitySyncFailed")
            return
        detail_batch_id = _start_coaching_detail_batch(session, run.user_id, connection.id,
            summary, workflow_input['timezone_name'], saved_sync.id)
        from src.application.coaching_refresh import CoachingRefreshService
        sync_day = _utc_now().astimezone(ZoneInfo(workflow_input["timezone_name"])).date()
        CoachingRefreshService(session).record_sync(
            user_id=run.user_id, summary=summary, today=sync_day,
            timezone_name=workflow_input["timezone_name"],
            source_sync_run_id=saved_sync.id,
            exclude_review_date=(date.fromisoformat(workflow_input["publication_date"])
                                 if run.workflow_name == "daily_review" else None),
        )
        if detail_batch_id is None:
            _enqueue_coaching_generation(session, run=run, workflow_input=workflow_input,
                                         source_sync_run_id=saved_sync.id)
        else:
            finalizer = session.scalar(select(AgentTaskModel).where(
                AgentTaskModel.idempotency_key == f'{ACTIVITY_DETAIL_FINALIZE_TASK}:{detail_batch_id}').with_for_update())
            if finalizer is not None:
                finalizer.payload = {**(finalizer.payload or {}),
                    'coaching_continuation': {'user_id': run.user_id, 'run_id': run.id,
                        'workflow_input': dict(workflow_input),
                        'source_sync_run_id': saved_sync.id}}
        queue.complete(task.id, now=_utc_now())
    except Exception as exc:
        running = integrations.get_running_sync_run_for_connection(connection.id)
        if running is not None:
            integrations.fail_sync_run(running.id, "Garmin sync failed")
        _fail_coaching_sync(session, task, run, type(exc).__name__)


def _fail_coaching_sync(session: Session, task: AgentTaskModel, run: AgentRun,
                        reason: str) -> None:
    if run.workflow_name == "daily_review":
        slot = session.scalar(select(TrainingReviewModel).where(
            TrainingReviewModel.user_id == run.user_id,
            TrainingReviewModel.reserved_run_id == run.id,
        ))
    else:
        slot = session.scalar(select(WorkoutAdviceModel).where(
            WorkoutAdviceModel.user_id == run.user_id,
            WorkoutAdviceModel.reserved_run_id == run.id,
        ))
    if slot is not None:
        slot.attempt_state = "sync_failed"
        slot.attempt_error = reason
        slot.freshness = "stale"
    queue = SqlAlchemyAgentTaskQueue(session)
    queue.fail(task.id, error_type=reason, error_message="Activity sync failed",
               retryable=False, now=_utc_now(), retry_delay=DEFAULT_RETRY_DELAY)
    SqlAlchemyAgentRunRepository(session).fail_run(run.fail(
        error_type=reason, error_message="Activity sync failed"))


def _build_garmin_sync_adapter(session: Session, integrations: SqlAlchemyIntegrationRepository):
    return GarminConnectResourceAdapter(credentials=integrations, cipher=load_garmin_credential_cipher())


def _process_daily_advice_sync(session: Session, task: AgentTaskModel) -> None:
    queue = SqlAlchemyAgentTaskQueue(session)
    payload = task.payload or {}
    run_id = payload.get("run_id")
    raw_anchor = (payload.get("input") or {}).get("anchor_date")
    try:
        anchor_date = date.fromisoformat(raw_anchor)
    except (TypeError, ValueError):
        queue.fail(task.id, error_type="MalformedTaskPayload", error_message="daily advice sync needs an anchor date",
                   retryable=False, now=_utc_now(), retry_delay=DEFAULT_RETRY_DELAY)
        return
    run_model = session.get(AgentRunModel, run_id) if run_id else None
    if run_model is None:
        queue.fail(task.id, error_type="MalformedTaskPayload", error_message="daily advice sync needs an agent run",
                   retryable=False, now=_utc_now(), retry_delay=DEFAULT_RETRY_DELAY)
        return
    runs = SqlAlchemyAgentRunRepository(session)
    run = runs.get_run_for_user(run_model.user_id, run_id)
    if run is None:
        queue.fail(task.id, error_type="MalformedTaskPayload", error_message="daily advice sync run owner is invalid",
                   retryable=False, now=_utc_now(), retry_delay=DEFAULT_RETRY_DELAY)
        return
    integrations = SqlAlchemyIntegrationRepository(session)
    connections = [item for item in integrations.list_active_connections_for_user(run.user_id)
                   if item.provider == "garmin_connect"]
    if not connections:
        _enqueue_daily_advice_generation(
            session, run=run, anchor_date=anchor_date, source_sync_run_id=None,
            limited_recovery=True, observed_at=_utc_now(),
        )
        queue.complete(task.id, now=_utc_now())
        return
    connection = connections[0]
    if connection.sync_status == "running":
        _defer_daily_advice_sync(session, task.id)
        return
    if connection.credential_status == "requires_reauth":
        _fail_daily_advice_sync(session, run=run, anchor_date=anchor_date,
                                source_sync_run_id=None, error_type="GarminRequiresReauth")
        queue.fail(task.id, error_type="GarminRequiresReauth", error_message="Garmin connection requires reauth",
                   retryable=False, now=_utc_now(), retry_delay=DEFAULT_RETRY_DELAY)
        return
    sync_run_id = None
    try:
        try:
            sync_run = integrations.start_sync_run(connection.id)
        except SyncAlreadyRunningError:
            _defer_daily_advice_sync(session, task.id)
            return
        sync_run_id = sync_run.id
        # Publish the running lease before a network request so another caller cannot start a sync.
        session.commit()
        adapter = _build_garmin_sync_adapter(session, integrations)
        summary = GarminInitialSyncHandler(
            normalize_training_evidence=normalize_garmin_training_evidence,
            integrations=integrations, activities=SqlAlchemyActivityRepository(session),
            outbox=SqlAlchemyOutboxRepository(session), garmin=adapter,
            athlete_profiles=SqlAlchemyAthleteRaceRepository(session),
            normalize_activity=lambda user_id, connection_id, activity: normalize_garmin_activity(
                user_id=user_id, provider_connection_id=connection_id, payload=activity,
            ),
            normalize_health=lambda user_id, health: normalize_garmin_daily_health(
                user_id=user_id, payload=health,
            ),
        ).handle(GarminInitialSyncCommand(
            user_id=run.user_id, connection_id=connection.id, as_of=_utc_now(), sync_run_id=sync_run_id,
        ))
        sync_run = integrations.get_latest_sync_run_for_connection(connection.id)
        refreshed = integrations.get_connection_for_user(run.user_id, connection.id)
        if sync_run is None or refreshed is None or not activity_sync_usable(
            summary, sync_run.status, refreshed.credential_status,
        ):
            _fail_daily_advice_sync(session, run=run, anchor_date=anchor_date,
                                    source_sync_run_id=sync_run_id, error_type="ActivitySyncFailed")
            queue.fail(task.id, error_type="ActivitySyncFailed", error_message="Garmin activities were not refreshed",
                       retryable=False, now=_utc_now(), retry_delay=DEFAULT_RETRY_DELAY)
            return
        _enqueue_daily_advice_generation(
            session, run=run, anchor_date=anchor_date, source_sync_run_id=sync_run_id,
            limited_recovery=recovery_data_limited(summary), observed_at=sync_run.finished_at or _utc_now(),
        )
        queue.complete(task.id, now=_utc_now())
    except Exception as exc:
        running = integrations.get_running_sync_run_for_connection(connection.id)
        if running is not None:
            integrations.fail_sync_run(running.id, "Garmin sync failed")
            sync_run_id = running.id
        _fail_daily_advice_sync(session, run=run, anchor_date=anchor_date,
                                source_sync_run_id=sync_run_id, error_type=type(exc).__name__)
        queue.fail(task.id, error_type=type(exc).__name__, error_message=str(exc),
                   retryable=False, now=_utc_now(), retry_delay=DEFAULT_RETRY_DELAY)


def _defer_daily_advice_sync(session: Session, task_id: str) -> None:
    model = session.get(AgentTaskModel, task_id)
    model.status = "queued"
    model.claimed_at = None
    model.available_at = _utc_now() + DEFAULT_RETRY_DELAY
    session.flush()


def _fail_daily_advice_sync(
    session: Session, *, run: AgentRun, anchor_date: date,
    source_sync_run_id: str | None, error_type: str,
) -> None:
    advice = SqlAlchemyDailyAdviceRepository(session)
    version = RefreshVersion(observed_at=_utc_now(), run_id=run.id)
    if advice.begin_refresh(run.user_id, anchor_date, version, source_sync_run_id):
        advice.mark_failed(run.user_id, anchor_date, version, "sync_failed")
    SqlAlchemyAgentRunRepository(session).fail_run(run.fail(
        error_type=error_type, error_message="activity synchronization did not provide usable data",
    ))


def _process_training_plan_daily_check(session: Session, task: AgentTaskModel) -> None:
    queue = SqlAlchemyAgentTaskQueue(session)
    task_id = task.id
    anchor_date = _daily_check_anchor_date(task.payload or {})
    if anchor_date is None:
        queue.fail(
            task_id,
            error_type="MalformedTaskPayload",
            error_message="training-plan.daily-check requires an ISO anchor_date",
            retryable=False,
            now=_utc_now(),
            retry_delay=DEFAULT_RETRY_DELAY,
        )
        return

    try:
        with session.begin_nested():
            service = _training_plan_regeneration_service(session)
            candidates = service.find_users_needing_projection(anchor_date)
    except Exception as exc:
        logger.exception("training plan daily check discovery failed", extra={"task_id": task_id})
        queue.fail(
            task_id,
            error_type=exc.__class__.__name__,
            error_message=str(exc),
            retryable=True,
            now=_utc_now(),
            retry_delay=DEFAULT_RETRY_DELAY,
        )
        return

    for candidate in candidates:
        try:
            with session.begin_nested():
                service.queue_background_generation(candidate)
        except Exception:
            logger.exception(
                "training plan background generation queue failed",
                extra={
                    "task_id": task_id,
                    "user_id": candidate.user_id,
                    "starts_on": candidate.strategy.starts_on.isoformat(),
                },
            )
    queue.complete(task_id, now=_utc_now())


def _daily_check_anchor_date(payload: dict) -> date | None:
    value = payload.get("anchor_date")
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _refresh_scheduled_training_plan_context(
    session: Session,
    *,
    runs: SqlAlchemyAgentRunRepository,
    run: AgentRun,
    workflow_name: str,
    workflow_input: dict,
) -> tuple[AgentRun, dict]:
    if workflow_name != "training_plan_generation" or run.metadata.get("manual_regeneration") is not False:
        return run, workflow_input

    previous_ends_on = (
        _optional_date(run.metadata.get("previous_ends_on"))
        or _optional_date(workflow_input.get("previous_ends_on"))
    )
    if previous_ends_on is None:
        previous_plan = SqlAlchemyTrainingPlanRepository(session).get_current_plan_for_user(run.user_id)
        if previous_plan is None:
            raise ValueError("scheduled training plan generation requires a previous active plan")
        previous_ends_on = previous_plan.ends_on

    strategy = _training_plan_regeneration_service(session).refresh_background_strategy(
        user_id=run.user_id,
        previous_ends_on=previous_ends_on,
    )
    refreshed_values = {
        "race_id": strategy.race_id,
        "plan_type": strategy.plan_type,
        "starts_on": strategy.starts_on.isoformat(),
        "plan_horizon_weeks": strategy.plan_horizon_weeks,
        "manual_regeneration": False,
        "trigger_type": "scheduled",
        "replace_active_projection": True,
        "previous_ends_on": previous_ends_on.isoformat(),
    }
    refreshed_run = runs.complete_run(
        replace(run, metadata={**run.metadata, **refreshed_values})
    )
    return refreshed_run, {**workflow_input, **refreshed_values}


def _dispatch_workflow(session: Session, run: AgentRun, workflow_name: str, workflow_input: dict) -> AgentRun:
    if workflow_name == "daily_review":
        publication_date = date.fromisoformat(workflow_input["publication_date"])
        timezone_name = workflow_input["timezone_name"]
        runs = SqlAlchemyAgentRunRepository(session)
        if run.status == "queued":
            run = runs.complete_run(run.mark_started())
        structured = run.prompt_version == PROMPT_VERSIONS['daily_review']
        gateway = (_queued_coaching_gateway(run) if structured else
            OpenAIModelGateway(model=run.model or "",
                api_key=load_openai_settings_for_queued_model(run.model or "").api_key)
            if run.provider == "openai" else None)
        request_id = workflow_input.get('generation_request_id')
        handler = GenerateTrainingReviewHandler(
            coaching=SqlAlchemyCoachingRepository(session),
            evidence=SqlAlchemyCoachingRepository(session),
            gateway=gateway,
            analysis_generator=generate_coaching_analysis if structured else None,
        )
        result = handler.handle(user_id=run.user_id, publication_date=publication_date,
                 timezone_name=timezone_name, run_id=run.id)
        if request_id:
            from src.application.coaching_refresh import CoachingRefreshService
            CoachingRefreshService(session).finish_review_request(
                request_id, result['evidence_fingerprint'])
        slot = SqlAlchemyCoachingRepository(session).get_review_slot(run.user_id, publication_date)
        published = slot['current']
        analysis_result = handler.last_analysis_result
        return runs.complete_run(replace(run,
            provider=(analysis_result.provider or (run.provider if analysis_result.analysis.analysis_mode == 'llm'
                else 'local')) if analysis_result else run.provider,
            model=(analysis_result.model or (run.model if analysis_result.analysis.analysis_mode == 'llm'
                else 'deterministic-local-companion')) if analysis_result else run.model,
            metadata={**run.metadata, "training_review_id": slot["id"], "result_state": "ready",
                **({'analysis_mode': published['analysis']['analysis_mode'],
                    'analysis_attempt_mode': analysis_result.analysis.analysis_mode,
                    'analysis_error_category': analysis_result.error_category,
                    'analysis_attempts': analysis_result.attempts,
                    'requested_provider': run.provider, 'requested_model': run.model}
                   if analysis_result else {}),
        }).complete(output_summary=published["narrative"],
                    token_usage=analysis_result.token_usage if analysis_result else None))
    if workflow_name == "workout_advice":
        advice_date = date.fromisoformat(workflow_input["advice_date"])
        runs = SqlAlchemyAgentRunRepository(session)
        if run.status == "queued":
            run = runs.complete_run(run.mark_started())
        structured = run.prompt_version == PROMPT_VERSIONS['workout_advice']
        gateway = _queued_coaching_gateway(run) if structured else None
        handler = GenerateWorkoutAdviceHandler(
            coaching=SqlAlchemyCoachingRepository(session),
            plans=SqlAlchemyTrainingPlanRepository(session),
            activities=SqlAlchemyActivityRepository(session),
            gateway=gateway,
            analysis_generator=generate_coaching_analysis if structured else None,
        )
        result = handler.handle(user_id=run.user_id, advice_date=advice_date,
                 timezone_name=workflow_input["timezone_name"],
                 workout_id=workflow_input.get("workout_id"),
                 constraints=WorkoutAdviceConstraints(**workflow_input["constraints"]),
                 run_id=run.id,
                 activity_sync_usable=(workflow_input.get("source_sync_run_id") is not None
                                       or workflow_input.get("manual_only") is True))
        slot_key = result.get("workout_id") or "no-workout"
        slot = SqlAlchemyCoachingRepository(session).get_advice_slot(run.user_id, advice_date, slot_key)
        analysis_result = handler.last_analysis_result
        return runs.complete_run(replace(run,
            provider=(analysis_result.provider or (run.provider if analysis_result.analysis.analysis_mode == 'llm'
                else 'local')) if analysis_result else run.provider,
            model=(analysis_result.model or (run.model if analysis_result.analysis.analysis_mode == 'llm'
                else 'deterministic-local-companion')) if analysis_result else run.model,
            metadata={**run.metadata, "workout_advice_id": slot["id"], "result_state": "ready",
                **({'analysis_mode': result['analysis']['analysis_mode'],
                    'analysis_attempt_mode': analysis_result.analysis.analysis_mode,
                    'analysis_error_category': analysis_result.error_category,
                    'analysis_attempts': analysis_result.attempts,
                    'requested_provider': run.provider, 'requested_model': run.model}
                   if analysis_result else {}),
        }).complete(output_summary=result["guidance"],
                    token_usage=analysis_result.token_usage if analysis_result else None,
                    recommendation_id=result.get("recommendation_id")))
    if workflow_name == "daily_recommendation":
        anchor = workflow_input.get("anchor_date")
        anchor_date = date.fromisoformat(anchor) if isinstance(anchor, str) else date.today()
        activities = SqlAlchemyActivityRepository(session)
        plans = SqlAlchemyTrainingPlanRepository(session)
        profiles = SqlAlchemyAthleteRaceRepository(session)
        gateway = (
            OpenAIModelGateway(
                model=run.model or "",
                api_key=load_openai_settings_for_queued_model(run.model or "").api_key,
            ) if run.provider == "openai" else LocalCompanionModelGateway()
        )
        handler = GenerateDailyAdviceHandler(
            training_plans=plans, training_data=activities,
            today_context=BuildTodayContextHandler(training_data=activities, training_plans=plans),
            advice=SqlAlchemyDailyAdviceRepository(session), runs=SqlAlchemyAgentRunRepository(session),
            gateway=gateway,
            timezone_for_user=lambda user_id: (
                profile.timezone if (profile := profiles.get_profile_for_user(user_id)) else "UTC"
            ),
            prompt_version=run.prompt_version,
        )
        return handler.handle(
            user_id=run.user_id, anchor_date=anchor_date, run=run,
            version=RefreshVersion(
                observed_at=(datetime.fromisoformat(workflow_input["refresh_observed_at"])
                             if workflow_input.get("refresh_observed_at") else _utc_now()),
                run_id=run.id,
            ),
            source_sync_run_id=workflow_input.get("source_sync_run_id"),
            limited_recovery=workflow_input.get("limited_recovery") is True,
        )
    agent = build_request_companion_agent(session, provider=run.provider, model=run.model)
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
