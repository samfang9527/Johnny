from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import logging
import sys

import pytest

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import scripts.agent_runtime as agent_runtime
from scripts.agent_runtime import main, schedule_once, work_drain
from src.application.async_agent_runs import QueueAgentRunHandler
from src.domain.agent_runtime import ModelResponse, ToolCallRequest
from src.domain.daily_advice import AdviceSections, DailyAdvice, RefreshVersion, WeekExecution, WorkoutGuide
from src.application.training_plan_regeneration import BackgroundProjectionCandidate, RegenerationStrategy
from src.api.dependencies import get_session
from src.application.interfaces.task_queue import TaskEnvelope
from src.api.dependencies import CurrentUser, ensure_current_user
from src.infrastructure.database.agent_run_repository import SqlAlchemyAgentRunRepository
from src.infrastructure.database.agent_task_queue import SqlAlchemyAgentTaskQueue
from src.infrastructure.database.daily_advice_repository import SqlAlchemyDailyAdviceRepository
from src.infrastructure.database.integration_repository import SqlAlchemyIntegrationRepository
from src.infrastructure.database.models import (
    AgentRunModel,
    AgentTaskModel,
    ActivityModel,
    Base,
    DailyAdviceModel,
    IntegrationConnectionModel,
    RaceModel,
    RecommendationModel,
    TrainingPlanModel,
    TrainingReviewModel,
    UserModel,
    WorkoutModel,
)
from src.infrastructure.database.uow import SqlAlchemyUnitOfWork
from src.main import create_app


def _create_context_ready_user(session, user_id: str, *, timezone_name: str = "UTC") -> None:
    ensure_current_user(session, CurrentUser(id=user_id))
    session.execute(
        TrainingPlanModel.__table__.insert().values(
            id=f"plan-{user_id}",
            user_id=user_id,
            name="Active Plan",
            status="active",
            starts_on=date(2027, 1, 1),
            ends_on=date(2027, 2, 28),
        )
    )
    session.execute(
        Base.metadata.tables["athlete_profiles"].insert().values(
            id=f"profile-{user_id}",
            user_id=user_id,
            timezone=timezone_name,
            experience_level="intermediate",
            metadata_json={},
        )
    )


def test_schedule_once_queues_independent_reviews_at_local_four(sqlite_session_factory) -> None:
    Base.metadata.create_all(sqlite_session_factory.kw["bind"])
    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        _create_context_ready_user(uow.session, "taipei", timezone_name="Asia/Taipei")
        _create_context_ready_user(uow.session, "utc")
        instant = datetime(2027, 1, 28, 3, 59, tzinfo=timezone.utc)
        schedule_once(uow.session, now=instant)
        early = list(uow.session.scalars(select(AgentTaskModel).where(
            AgentTaskModel.task_type == "coaching.sync")))
        assert {task.payload["input"]["timezone_name"] for task in early} == {"Asia/Taipei"}
        schedule_once(uow.session, now=instant + timedelta(minutes=1))
        schedule_once(uow.session, now=instant + timedelta(minutes=1))
        tasks = list(uow.session.scalars(select(AgentTaskModel).where(
            AgentTaskModel.task_type == "coaching.sync")))
        assert len(tasks) == 2
        assert {task.payload["workflow_name"] for task in tasks} == {"daily_review"}
        assert {task.payload["input"]["publication_date"] for task in tasks} == {"2027-01-28"}
        assert not list(uow.session.scalars(select(AgentTaskModel).where(
            AgentTaskModel.task_type == "daily_advice.sync")))


def test_v2_scheduled_local_review_records_rules_mode_and_prompt(sqlite_session_factory, monkeypatch) -> None:
    monkeypatch.setenv('JOHNNY_COACHING_ANALYSIS_V2_ENABLED', 'true')
    monkeypatch.delenv('LLM_API_KEY', raising=False)
    monkeypatch.delenv('OPENAI_API_KEY', raising=False)
    Base.metadata.create_all(sqlite_session_factory.kw['bind'])
    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        _create_context_ready_user(uow.session, 'v2-local')
        today = datetime.now(timezone.utc).date()
        schedule_once(uow.session, now=datetime.combine(today, datetime.min.time(),
                      tzinfo=timezone.utc) + timedelta(hours=4))
        assert work_drain(uow.session, max_tasks=3) >= 2
        run = uow.session.scalar(select(AgentRunModel).where(
            AgentRunModel.user_id == 'v2-local', AgentRunModel.workflow_name == 'daily_review'))
        assert run.prompt_version == 'johnny-review-analysis-v2'
        assert run.metadata_json['analysis_mode'] == 'rules'
        assert run.provider == 'local'
        from src.infrastructure.database.coaching_repository import SqlAlchemyCoachingRepository
        result = SqlAlchemyCoachingRepository(uow.session).get_review_slot('v2-local', today)['current']
        assert result['analysis']['fallback_reason'] == 'disabled'


def test_v2_advice_worker_records_model_usage_and_falls_back_if_credentials_disappear(
        sqlite_session_factory, monkeypatch) -> None:
    import json
    from src.application.coaching_analysis_generation import PROMPT_VERSIONS
    from src.domain.agent_runtime import AgentRun, TokenUsage
    from src.infrastructure.database.coaching_repository import SqlAlchemyCoachingRepository

    Base.metadata.create_all(sqlite_session_factory.kw['bind'])
    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        ensure_current_user(uow.session, CurrentUser(id='v2-advice'))
        today = datetime.now(timezone.utc).date()
        request = dict(advice_date=today.isoformat(), timezone_name='UTC', workout_id=None,
                       constraints={}, manual_only=True)

        class Gateway:
            def __init__(self, **kwargs):
                pass

            def complete(self, model_request):
                return ModelResponse(content=json.dumps({
                    'headline': '先確認今日安排', 'summary': '依身體狀況保守安排。',
                    'findings': [{'observation': '今天沒有課表。',
                                  'interpretation': '先檢視目前安排。',
                                  'evidence_refs': ['evidence:window']}],
                    'actions': [{'action_id': 'rest', 'text': '先休息並確認安排。',
                                 'evidence_refs': ['evidence:window']}],
                    'limitations': [], 'evidence_refs': ['evidence:window'],
                }, ensure_ascii=False), provider='openai', model='fake-model',
                    token_usage=TokenUsage(input_tokens=5, output_tokens=7))

        monkeypatch.setattr(agent_runtime, 'OpenAIModelGateway', Gateway)
        monkeypatch.setenv('LLM_API_KEY', 'fake-key')
        run_store = SqlAlchemyAgentRunRepository(uow.session)
        run = run_store.create_run(AgentRun.queue(user_id='v2-advice', trigger_type='manual',
            workflow_name='workout_advice', prompt_version=PROMPT_VERSIONS['workout_advice'],
            provider='openai', model='fake-model'))
        completed = agent_runtime._dispatch_workflow(uow.session, run, 'workout_advice', request)
        assert completed.metadata['analysis_mode'] == 'llm'
        assert completed.metadata['requested_model'] == 'fake-model'
        assert (completed.input_tokens, completed.output_tokens) == (5, 7)
        result = SqlAlchemyCoachingRepository(uow.session).get_advice_slot(
            'v2-advice', today, 'no-workout')['current']
        assert result['analysis']['analysis_mode'] == 'llm'
        assert result['analysis_provenance']['token_usage']['total_tokens'] == 12

        monkeypatch.delenv('LLM_API_KEY')
        fallback_run = run_store.create_run(AgentRun.queue(user_id='v2-advice', trigger_type='manual',
            workflow_name='workout_advice', prompt_version=PROMPT_VERSIONS['workout_advice'],
            provider='openai', model='fake-model'))
        fallback = agent_runtime._dispatch_workflow(
            uow.session, fallback_run, 'workout_advice', request)
        assert fallback.metadata['analysis_mode'] == 'llm'  # unchanged evidence reuses published revision
        assert fallback.metadata['analysis_attempt_mode'] == 'rules'
        assert fallback.metadata['analysis_error_category'] == 'provider_error'
        assert fallback.metadata['requested_provider'] == 'openai'
        assert fallback.provider == 'local'
        expired_run = run_store.create_run(AgentRun.queue(user_id='v2-advice', trigger_type='manual',
            workflow_name='workout_advice', prompt_version=PROMPT_VERSIONS['workout_advice'],
            provider='local', model='deterministic-local-companion'))
        with pytest.raises(ValueError, match='request_date_expired'):
            agent_runtime._dispatch_workflow(uow.session, expired_run, 'workout_advice',
                {**request, 'advice_date': (today - timedelta(days=1)).isoformat()})


def test_smoke_defaults_to_current_daily_review_not_retired_advice(sqlite_session_factory) -> None:
    Base.metadata.create_all(sqlite_session_factory.kw["bind"])
    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        _create_context_ready_user(uow.session, "review-smoke")
        assert agent_runtime.smoke(uow.session, user_id="review-smoke", timeout_seconds=5) == 0
        review = uow.session.scalar(select(TrainingReviewModel).where(
            TrainingReviewModel.user_id == "review-smoke"))
        assert review is not None
        assert review.current_revision_id is not None
        assert not uow.session.scalar(select(AgentTaskModel.id).where(
            AgentTaskModel.task_type == "daily_advice.sync"))


def test_scheduled_review_without_provider_preserves_uncertainty_and_creates_no_proposal(sqlite_session_factory) -> None:
    from src.infrastructure.database.coaching_repository import SqlAlchemyCoachingRepository

    Base.metadata.create_all(sqlite_session_factory.kw["bind"])
    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        _create_context_ready_user(uow.session, "no-provider")
        today = datetime.now(timezone.utc).date()
        schedule_once(uow.session, now=datetime.combine(today, datetime.min.time(), tzinfo=timezone.utc)
                      + timedelta(hours=4))
        assert work_drain(uow.session, max_tasks=3) >= 2
        review = SqlAlchemyCoachingRepository(uow.session).get_review_slot("no-provider", today)
        assert review["current"]["kind"] == "daily_review"
        assert review["current"]["score"]["value"] is None
        assert not list(uow.session.scalars(select(RecommendationModel).where(
            RecommendationModel.user_id == "no-provider")))


def test_scheduler_training_plan_queue_uses_resolved_provider(sqlite_session_factory, monkeypatch) -> None:
    Base.metadata.create_all(sqlite_session_factory.kw["bind"])
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("LLM_MODEL", "test-model")
    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        ensure_current_user(uow.session, CurrentUser(id="scheduled-provider-user"))
        handler = agent_runtime._training_plan_queue_handler(uow.session)
        result = handler.queue_run(
            user_id="scheduled-provider-user",
            workflow_name="training_plan_generation",
            trigger_type="scheduled",
            idempotency_key="scheduled-provider-test",
            payload={"plan_type": "base", "starts_on": "2027-01-01"},
        )
        uow.commit()

    assert (result.run.provider, result.run.model) == ("openai", "test-model")


def test_work_drain_daily_check_queues_one_background_generation_for_repeated_checks(sqlite_session_factory) -> None:
    Base.metadata.create_all(sqlite_session_factory.kw["bind"])
    anchor = datetime.now(timezone.utc).date()
    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        _create_context_ready_user(uow.session, "background-user")
        uow.session.execute(
            TrainingPlanModel.__table__.update()
            .where(TrainingPlanModel.id == "plan-background-user")
            .values(
                starts_on=anchor - timedelta(days=34),
                ends_on=anchor - timedelta(days=7),
            )
        )
        queue = SqlAlchemyAgentTaskQueue(uow.session)
        for suffix in ("first", "repeat"):
            queue.enqueue(
                TaskEnvelope(
                    task_type="training-plan.daily-check",
                    payload={"anchor_date": anchor.isoformat()},
                    correlation_id=f"daily-check:{suffix}",
                    idempotency_key=f"daily-check:{anchor.isoformat()}:{suffix}",
                )
            )

        processed = work_drain(uow.session)
        generation_runs = list(
            uow.session.scalars(
                select(AgentRunModel).where(AgentRunModel.workflow_name == "training_plan_generation")
            )
        )
        generation_tasks = list(
            uow.session.scalars(
                select(AgentTaskModel).where(
                    AgentTaskModel.task_type == "agent.workflow",
                    AgentTaskModel.payload["workflow_name"].as_string() == "training_plan_generation",
                )
            )
        )
        uow.commit()

    assert processed == 3
    assert len(generation_runs) == 1
    assert len(generation_tasks) == 1
    assert generation_runs[0].metadata_json["manual_regeneration"] is False
    assert generation_runs[0].metadata_json["trigger_type"] == "scheduled"


def test_work_drain_daily_check_continues_after_candidate_queue_failure(sqlite_session_factory, monkeypatch, caplog) -> None:
    Base.metadata.create_all(sqlite_session_factory.kw["bind"])
    strategy = RegenerationStrategy(
        race_id=None,
        plan_type="maintenance",
        reason="no_future_race",
        starts_on=date(2027, 2, 1),
        plan_horizon_weeks=4,
    )
    failed_candidate = BackgroundProjectionCandidate(
        user_id="failed-user",
        previous_plan_id="failed-plan",
        previous_ends_on=date(2027, 1, 24),
        strategy=strategy,
    )
    succeeding_candidate = BackgroundProjectionCandidate(
        user_id="succeeding-user",
        previous_plan_id="succeeding-plan",
        previous_ends_on=date(2027, 1, 24),
        strategy=strategy,
    )

    class BackgroundService:
        def find_users_needing_projection(self, today):
            assert today == date(2027, 1, 31)
            return [failed_candidate, succeeding_candidate]

        def queue_background_generation(self, candidate):
            if candidate.user_id == "failed-user":
                raise ConnectionError("background queue unavailable")
            queued_user_ids.append(candidate.user_id)

    queued_user_ids: list[str] = []
    monkeypatch.setattr(agent_runtime, "_training_plan_regeneration_service", lambda session: BackgroundService())

    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        queue = SqlAlchemyAgentTaskQueue(uow.session)
        task = queue.enqueue(
            TaskEnvelope(
                task_type="training-plan.daily-check",
                payload={"anchor_date": "2027-01-31"},
                correlation_id="daily-check-candidate-failure",
                idempotency_key="daily-check-candidate-failure",
            )
        )

        processed = work_drain(uow.session)
        persisted_task = uow.session.get(AgentTaskModel, task.id)
        uow.commit()

    assert processed == 1
    assert queued_user_ids == ["succeeding-user"]
    assert persisted_task.status == "completed"
    assert "training plan background generation queue failed" in caplog.text


def test_work_drain_daily_check_retries_discovery_failure(sqlite_session_factory, monkeypatch, caplog) -> None:
    Base.metadata.create_all(sqlite_session_factory.kw["bind"])

    class UnavailableBackgroundService:
        def find_users_needing_projection(self, today):
            raise ConnectionError("database unavailable")

    monkeypatch.setattr(
        agent_runtime,
        "_training_plan_regeneration_service",
        lambda session: UnavailableBackgroundService(),
    )

    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        queue = SqlAlchemyAgentTaskQueue(uow.session)
        task = queue.enqueue(
            TaskEnvelope(
                task_type="training-plan.daily-check",
                payload={"anchor_date": "2027-01-31"},
                correlation_id="daily-check-discovery-failure",
                idempotency_key="daily-check-discovery-failure",
            )
        )

        processed = work_drain(uow.session)
        persisted_task = uow.session.get(AgentTaskModel, task.id)
        uow.commit()

    assert processed == 1
    assert persisted_task.status == "queued"
    assert persisted_task.retry_count == 1
    assert persisted_task.last_error_type == "ConnectionError"
    assert "training plan daily check discovery failed" in caplog.text


def test_work_drain_daily_check_isolates_database_discovery_failure(
    sqlite_session_factory,
    monkeypatch,
) -> None:
    Base.metadata.create_all(sqlite_session_factory.kw["bind"])

    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        ensure_current_user(uow.session, CurrentUser(id="discovery-owner"))
        uow.commit()

    class DatabaseFailingBackgroundService:
        def __init__(self, session) -> None:
            self._session = session

        def find_users_needing_projection(self, today):
            self._session.add(
                UserModel(
                    id="duplicate-discovery-email",
                    email="discovery-owner@local.johnny",
                    display_name="Duplicate",
                )
            )
            self._session.flush()

    monkeypatch.setattr(
        agent_runtime,
        "_training_plan_regeneration_service",
        lambda session: DatabaseFailingBackgroundService(session),
    )

    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        task = SqlAlchemyAgentTaskQueue(uow.session).enqueue(
            TaskEnvelope(
                task_type="training-plan.daily-check",
                payload={"anchor_date": "2027-01-31"},
                correlation_id="daily-check-database-discovery-failure",
                idempotency_key="daily-check-database-discovery-failure",
            )
        )

        processed = work_drain(uow.session)
        persisted_task = uow.session.get(AgentTaskModel, task.id)
        uow.commit()

    assert processed == 1
    assert persisted_task.status == "queued"
    assert persisted_task.retry_count == 1
    assert persisted_task.last_error_type == "IntegrityError"


def test_work_drain_daily_check_isolates_database_queue_failure_per_candidate(
    sqlite_session_factory,
    monkeypatch,
) -> None:
    Base.metadata.create_all(sqlite_session_factory.kw["bind"])
    strategy = RegenerationStrategy(
        race_id=None,
        plan_type="maintenance",
        reason="no_future_race",
        starts_on=date(2027, 2, 1),
        plan_horizon_weeks=4,
    )
    candidates = [
        BackgroundProjectionCandidate(
            user_id="database-failure-user",
            previous_plan_id="database-failure-plan",
            previous_ends_on=date(2027, 1, 24),
            strategy=strategy,
        ),
        BackgroundProjectionCandidate(
            user_id="database-success-user",
            previous_plan_id="database-success-plan",
            previous_ends_on=date(2027, 1, 24),
            strategy=strategy,
        ),
    ]

    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        ensure_current_user(uow.session, CurrentUser(id="queue-owner"))
        uow.commit()

    queued_user_ids: list[str] = []

    class DatabaseFailingBackgroundService:
        def __init__(self, session) -> None:
            self._session = session

        def find_users_needing_projection(self, today):
            return candidates

        def queue_background_generation(self, candidate):
            if candidate.user_id == "database-failure-user":
                self._session.add(
                    UserModel(
                        id="duplicate-queue-email",
                        email="queue-owner@local.johnny",
                        display_name="Duplicate",
                    )
                )
                self._session.flush()
            self._session.scalar(select(UserModel.id).where(UserModel.id == "queue-owner"))
            queued_user_ids.append(candidate.user_id)

    monkeypatch.setattr(
        agent_runtime,
        "_training_plan_regeneration_service",
        lambda session: DatabaseFailingBackgroundService(session),
    )

    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        task = SqlAlchemyAgentTaskQueue(uow.session).enqueue(
            TaskEnvelope(
                task_type="training-plan.daily-check",
                payload={"anchor_date": "2027-01-31"},
                correlation_id="daily-check-database-candidate-failure",
                idempotency_key="daily-check-database-candidate-failure",
            )
        )

        processed = work_drain(uow.session)
        persisted_task = uow.session.get(AgentTaskModel, task.id)
        uow.commit()

    assert processed == 1
    assert queued_user_ids == ["database-success-user"]
    assert persisted_task.status == "completed"


def test_scheduled_training_plan_refreshes_stale_dates_and_race_before_execution(
    sqlite_session_factory,
    monkeypatch,
) -> None:
    Base.metadata.create_all(sqlite_session_factory.kw["bind"])
    execution_instant = datetime(2027, 1, 10, 12, tzinfo=timezone.utc)
    previous_ends_on = date(2027, 1, 1)
    stale_starts_on = date(2027, 1, 9)
    refreshed_starts_on = date(2027, 1, 11)
    monkeypatch.setattr(agent_runtime, "_utc_now", lambda: execution_instant)

    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        _create_context_ready_user(uow.session, "refresh-user")
        uow.session.execute(
            TrainingPlanModel.__table__.update()
            .where(TrainingPlanModel.id == "plan-refresh-user")
            .values(
                starts_on=previous_ends_on - timedelta(days=27),
                ends_on=previous_ends_on,
            )
        )
        uow.session.execute(
            RaceModel.__table__.insert(),
            [
                {
                    "id": "cancelled-primary",
                    "user_id": "refresh-user",
                    "name": "Cancelled Primary",
                    "race_date": date(2027, 2, 1),
                    "distance_meters": 21097,
                    "status": "cancelled",
                    "metadata_json": {"priority": "primary"},
                },
                {
                    "id": "active-secondary",
                    "user_id": "refresh-user",
                    "name": "Active Secondary",
                    "race_date": date(2027, 2, 15),
                    "distance_meters": 21097,
                    "status": "active",
                    "metadata_json": {"priority": "secondary"},
                },
                {
                    "id": "planned-primary",
                    "user_id": "refresh-user",
                    "name": "Planned Primary",
                    "race_date": date(2027, 3, 1),
                    "distance_meters": 21097,
                    "status": "planned",
                    "metadata_json": {"priority": "primary"},
                },
            ],
        )
        queued = QueueAgentRunHandler(
            runs=SqlAlchemyAgentRunRepository(uow.session),
            queue=SqlAlchemyAgentTaskQueue(uow.session),
            prompt_version="running-companion-v1",
            provider="local",
            model="deterministic-local-companion",
        ).queue_run(
            user_id="refresh-user",
            workflow_name="training_plan_generation",
            trigger_type="scheduled",
            idempotency_key="training_plan_generation:refresh-user",
            payload={
                "race_id": "cancelled-primary",
                "plan_type": "race",
                "starts_on": stale_starts_on.isoformat(),
                "plan_horizon_weeks": 4,
                "manual_regeneration": False,
                "trigger_type": "scheduled",
                "replace_active_projection": True,
                "previous_ends_on": previous_ends_on.isoformat(),
            },
            requeue_terminal=True,
        )

        processed = work_drain(uow.session)
        refreshed_run = uow.session.get(AgentRunModel, queued.run.id)
        refreshed_task = uow.session.get(AgentTaskModel, queued.task.id)
        generated_plan = uow.session.scalar(
            select(TrainingPlanModel).where(
                TrainingPlanModel.user_id == "refresh-user",
                TrainingPlanModel.status == "active",
            )
        )
        previous_plan = uow.session.get(TrainingPlanModel, "plan-refresh-user")
        uow.commit()

    assert processed == 1
    assert refreshed_run.status == "completed"
    assert refreshed_run.metadata_json["race_id"] == "planned-primary"
    assert refreshed_run.metadata_json["starts_on"] == refreshed_starts_on.isoformat()
    assert refreshed_run.metadata_json["plan_type"] == "race"
    assert refreshed_run.metadata_json["replace_active_projection"] is True
    assert refreshed_task.payload["input"]["race_id"] == "planned-primary"
    assert refreshed_task.payload["input"]["starts_on"] == refreshed_starts_on.isoformat()
    assert generated_plan is not None
    assert generated_plan.race_id == "planned-primary"
    assert generated_plan.starts_on == refreshed_starts_on
    assert previous_plan.status == "superseded"


def test_legacy_scheduled_training_plan_derives_previous_end_before_execution(
    sqlite_session_factory,
    monkeypatch,
) -> None:
    Base.metadata.create_all(sqlite_session_factory.kw["bind"])
    execution_instant = datetime(2027, 1, 10, 12, tzinfo=timezone.utc)
    previous_ends_on = date(2027, 1, 1)
    refreshed_starts_on = date(2027, 1, 11)
    monkeypatch.setattr(agent_runtime, "_utc_now", lambda: execution_instant)

    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        _create_context_ready_user(uow.session, "legacy-refresh-user")
        uow.session.execute(
            TrainingPlanModel.__table__.update()
            .where(TrainingPlanModel.id == "plan-legacy-refresh-user")
            .values(
                starts_on=previous_ends_on - timedelta(days=27),
                ends_on=previous_ends_on,
            )
        )
        uow.session.execute(
            RaceModel.__table__.insert(),
            [
                {
                    "id": "legacy-completed-race",
                    "user_id": "legacy-refresh-user",
                    "name": "Completed Race",
                    "race_date": date(2027, 2, 1),
                    "distance_meters": 21097,
                    "status": "completed",
                    "metadata_json": {"priority": "primary"},
                },
                {
                    "id": "legacy-planned-race",
                    "user_id": "legacy-refresh-user",
                    "name": "Planned Race",
                    "race_date": date(2027, 2, 15),
                    "distance_meters": 21097,
                    "status": "planned",
                    "metadata_json": {"priority": "secondary"},
                },
            ],
        )
        queued = QueueAgentRunHandler(
            runs=SqlAlchemyAgentRunRepository(uow.session),
            queue=SqlAlchemyAgentTaskQueue(uow.session),
            prompt_version="running-companion-v1",
            provider="local",
            model="deterministic-local-companion",
        ).queue_run(
            user_id="legacy-refresh-user",
            workflow_name="training_plan_generation",
            trigger_type="scheduled",
            idempotency_key="training_plan_generation:legacy-refresh-user",
            payload={
                "race_id": "legacy-completed-race",
                "plan_type": "race",
                "starts_on": "2027-01-09",
                "plan_horizon_weeks": 4,
                "manual_regeneration": False,
                "trigger_type": "scheduled",
                "replace_active_projection": True,
            },
            requeue_terminal=True,
        )

        processed = work_drain(uow.session)
        refreshed_run = uow.session.get(AgentRunModel, queued.run.id)
        refreshed_task = uow.session.get(AgentTaskModel, queued.task.id)
        generated_plan = uow.session.scalar(
            select(TrainingPlanModel).where(
                TrainingPlanModel.user_id == "legacy-refresh-user",
                TrainingPlanModel.status == "active",
            )
        )
        uow.commit()

    assert processed == 1
    assert refreshed_run.status == "completed"
    assert refreshed_run.metadata_json["previous_ends_on"] == previous_ends_on.isoformat()
    assert refreshed_run.metadata_json["starts_on"] == refreshed_starts_on.isoformat()
    assert refreshed_run.metadata_json["race_id"] == "legacy-planned-race"
    assert refreshed_task.payload["input"]["previous_ends_on"] == previous_ends_on.isoformat()
    assert refreshed_task.payload["input"]["starts_on"] == refreshed_starts_on.isoformat()
    assert generated_plan is not None
    assert generated_plan.starts_on == refreshed_starts_on
    assert generated_plan.race_id == "legacy-planned-race"


def test_work_drain_retires_legacy_daily_task_and_keeps_training_plan_generation(sqlite_session_factory, caplog) -> None:
    Base.metadata.create_all(sqlite_session_factory.kw["bind"])
    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        _create_context_ready_user(uow.session, "worker-user")
        uow.session.add(WorkoutModel(
            id="worker-original-workout", training_plan_id="plan-worker-user",
            scheduled_for=date(2027, 1, 28), workout_type="easy_run",
            planned_duration_minutes=40, status="planned", details={"purpose": "建立有氧基礎"},
        ))
        handler_runs = SqlAlchemyAgentRunRepository(uow.session)
        queue = SqlAlchemyAgentTaskQueue(uow.session)
        handler = QueueAgentRunHandler(
            runs=handler_runs,
            queue=queue,
            prompt_version="running-companion-v1",
            provider="local",
            model="deterministic-local-companion",
        )
        daily = handler.queue_run(
            user_id="worker-user",
            workflow_name="daily_recommendation",
            trigger_type="manual",
            idempotency_key="daily:worker-user:2027-01-28",
            payload={"anchor_date": "2027-01-28"},
        )
        training = handler.queue_run(
            user_id="worker-user",
            workflow_name="training_plan_generation",
            trigger_type="manual",
            idempotency_key="training:worker-user:2027-01-28",
            payload={"plan_type": "base", "starts_on": "2027-01-01", "goal_notes": "private-runner-note"},
        )

        with caplog.at_level(logging.INFO, logger="scripts.agent_runtime"):
            processed = work_drain(uow.session)
        daily_run = handler_runs.get_run_for_user("worker-user", daily.run.id)
        training_run = handler_runs.get_run_for_user("worker-user", training.run.id)
        generated_plan = uow.session.scalar(
            select(TrainingPlanModel).where(
                TrainingPlanModel.user_id == "worker-user",
                TrainingPlanModel.name == "Johnny 訓練計畫",
            )
        )
        recommendation_count = len(uow.session.scalars(select(RecommendationModel)).all())
        advice = uow.session.scalar(select(DailyAdviceModel).where(DailyAdviceModel.user_id == "worker-user"))
        original_workout = uow.session.get(WorkoutModel, "worker-original-workout")
        daily_steps = handler_runs.list_steps_for_run(daily.run.id)
        uow.commit()

    assert processed == 2
    assert daily_run.status == "failed"
    assert daily_run.error_type == "LegacyDailyAdviceRetired"
    assert training_run.status == "completed"
    assert generated_plan is not None
    assert generated_plan.status == "active"
    assert generated_plan.metadata_json["phase_segments"] == [
        {"phase": "maintenance", "starts_on": "2027-01-01", "ends_on": "2027-01-28"}
    ]
    assert {workout.details["phase"] for workout in generated_plan.workouts} == {"maintenance"}
    assert recommendation_count == 0
    assert advice is None
    assert (original_workout.planned_duration_minutes, original_workout.status) == (40, "planned")
    assert daily_run.recommendation_id is None
    assert daily_steps == []
    assert "worker task claimed task_id=" in caplog.text
    assert f"worker workflow started run_id={training.run.id} workflow=training_plan_generation provider=local" in caplog.text
    assert f"worker workflow finished run_id={training.run.id} workflow=training_plan_generation status=completed" in caplog.text
    assert "worker task finished task_id=" in caplog.text
    assert "duration_ms=" in caplog.text
    assert "private-runner-note" not in caplog.text


def test_retired_daily_workflow_preserves_previous_advice(sqlite_session_factory) -> None:
    Base.metadata.create_all(sqlite_session_factory.kw["bind"])
    day = date(2027, 1, 28)
    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        _create_context_ready_user(uow.session, "invalid-advice-user")
        advice_store = SqlAlchemyDailyAdviceRepository(uow.session)
        old_version = RefreshVersion(datetime(2026, 1, 27, tzinfo=timezone.utc), "old-run")
        assert advice_store.begin_refresh("invalid-advice-user", day, old_version, None)
        assert advice_store.publish("invalid-advice-user", day, old_version, DailyAdvice(
            user_id="invalid-advice-user", advice_date=day, plan_version_id="plan-invalid-advice-user",
            workout_id=None, week_start=date(2027, 1, 22), week_end=day,
            execution_mode="rest", facts=WeekExecution(
                week_start=date(2027, 1, 22), week_end=day, status="on_plan",
                planned_count=0, completed_count=0, missed_count=0, extra_count=0,
                planned_minutes=None, actual_minutes=0, planned_distance_meters=None,
                actual_distance_meters=0, today_completed=False,
            ), sections=AdviceSections(
                week_summary="先前有效建議", today_execution="今天休息",
                workout_guide=WorkoutGuide("恢復", "輕鬆", "休息", "維持休息"),
            ), generated_at=datetime(2027, 1, 27, tzinfo=timezone.utc),
            source_sync_run_id=None, source_run_id="old-run", state="ready", data_freshness="limited",
        ))
        queued = QueueAgentRunHandler(
            runs=SqlAlchemyAgentRunRepository(uow.session), queue=SqlAlchemyAgentTaskQueue(uow.session),
            prompt_version="running-companion-v1", provider="local", model="deterministic-local-companion",
        ).queue_run(
            user_id="invalid-advice-user", workflow_name="daily_recommendation", trigger_type="manual",
            idempotency_key="invalid-daily-refresh", payload={"anchor_date": day.isoformat()},
        )
        assert work_drain(uow.session) == 1
        current = advice_store.get_for_user_date("invalid-advice-user", day)
        run_store = SqlAlchemyAgentRunRepository(uow.session)
        run = run_store.get_run_for_user("invalid-advice-user", queued.run.id)
        steps = run_store.list_steps_for_run(queued.run.id)
        uow.commit()

    assert run.status == "failed"
    assert run.recommendation_id is None
    assert run.error_type == "LegacyDailyAdviceRetired"
    assert current.state == "ready"
    assert current.data_freshness == "limited"
    assert current.sections.week_summary == "先前有效建議"
    assert current.source_run_id == "old-run"
    assert steps == []


def test_work_drain_marks_unknown_and_malformed_tasks_non_retryable(sqlite_session_factory) -> None:
    Base.metadata.create_all(sqlite_session_factory.kw["bind"])
    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        queue = SqlAlchemyAgentTaskQueue(uow.session)
        queue.enqueue(
            task=TaskEnvelope(
                task_type="unknown",
                payload={},
                correlation_id="unknown",
                idempotency_key="unknown",
            )
        )
        queue.enqueue(
            task=TaskEnvelope(
                task_type="training-plan.daily-check",
                payload={},
                correlation_id="daily-check-malformed",
                idempotency_key="daily-check-malformed",
            )
        )
        queue.enqueue(
            task=TaskEnvelope(
                task_type="agent.workflow",
                payload={"workflow_name": "training_plan_generation"},
                correlation_id="malformed",
                idempotency_key="malformed",
            )
        )

        processed = work_drain(uow.session)
        tasks = list(uow.session.scalars(select(AgentTaskModel).order_by(AgentTaskModel.created_at)))
        statuses = [task.status for task in tasks]
        errors = [task.last_error_type for task in tasks]
        retry_counts = [task.retry_count for task in tasks]
        uow.commit()

    assert processed == 3
    assert statuses == ["failed", "failed", "failed"]
    assert errors == ["UnknownTaskType", "MalformedTaskPayload", "MalformedTaskPayload"]
    assert retry_counts == [1, 1, 1]


def test_agent_runtime_cli_work_drain_does_not_require_smoke_openai_flag(tmp_path, monkeypatch, capsys) -> None:
    database_url = f"sqlite:///{tmp_path / 'agent-runtime-cli.db'}"
    monkeypatch.setattr(
        sys,
        "argv",
        ["agent_runtime.py", "--database-url", database_url, "work-drain"],
    )

    result = main()

    assert result == 0
    assert "processed=0" in capsys.readouterr().out


def test_agent_runtime_cli_worker_preserves_provider_environment(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setattr(
        sys, "argv",
        ["agent_runtime.py", "--database-url", f"sqlite:///{tmp_path / 'worker.db'}", "work-drain"],
    )

    assert main() == 0
    import os
    assert os.environ["LLM_PROVIDER"] == "openai"


def test_worker_uses_queued_local_provider_with_openai_environment(sqlite_session_factory, monkeypatch) -> None:
    from src.api.dependencies import build_request_companion_agent
    from src.infrastructure.llm.local_gateway import LocalCompanionModelGateway

    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("LLM_MODEL", "changed-model")
    with sqlite_session_factory() as session:
        agent = build_request_companion_agent(session, provider="local", model="deterministic-local-companion")
    assert isinstance(agent._model_gateway, LocalCompanionModelGateway)


def test_worker_uses_queued_openai_model_not_current_environment(sqlite_session_factory, monkeypatch) -> None:
    from src.api import dependencies

    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("LLM_MODEL", "changed-model")
    seen = []
    monkeypatch.setattr(dependencies, "build_running_companion_agent", lambda **kwargs: seen.append(kwargs["settings"]) or object())
    with sqlite_session_factory() as session:
        dependencies.build_request_companion_agent(session, provider="openai", model="queued-model")
    assert len(seen) == 1
    assert seen[0].model == "queued-model"


def test_worker_fails_queued_openai_run_without_key(sqlite_session_factory, monkeypatch, caplog) -> None:
    Base.metadata.create_all(sqlite_session_factory.kw["bind"])
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        ensure_current_user(uow.session, CurrentUser(id="missing-worker-key"))
        queued = QueueAgentRunHandler(
            runs=SqlAlchemyAgentRunRepository(uow.session),
            queue=SqlAlchemyAgentTaskQueue(uow.session),
            prompt_version="running-companion-v1", provider="openai", model="queued-model",
        ).queue_run(
            user_id="missing-worker-key", workflow_name="training_plan_generation",
            trigger_type="manual", idempotency_key="missing-worker-key",
            payload={"plan_type": "base", "starts_on": "2027-01-01"},
        )
        with caplog.at_level(logging.INFO, logger="scripts.agent_runtime"):
            assert work_drain(uow.session) == 1
        run = uow.session.get(AgentRunModel, queued.run.id)
        task = uow.session.scalar(select(AgentTaskModel).where(AgentTaskModel.payload["run_id"].as_string() == run.id))
        assert run.status == "failed"
        assert task.status == "failed"
        assert run.provider == "openai"
        assert "required" in run.error_message
        assert f"worker workflow started run_id={run.id} workflow=training_plan_generation provider=openai" in caplog.text
        assert f"worker workflow raised run_id={run.id} workflow=training_plan_generation error_type=" in caplog.text
        assert "status=failed" in caplog.text
        assert "OPENAI_API_KEY" not in caplog.text


def test_worker_rejects_unknown_persisted_provider(sqlite_session_factory) -> None:
    from src.api.dependencies import build_request_companion_agent

    with sqlite_session_factory() as session:
        try:
            build_request_companion_agent(session, provider="other", model="unknown")
        except ValueError as exc:
            assert "provider" in str(exc).lower()
        else:
            assert False, "unknown provider should fail"


def test_smoke_flow_queues_with_http_drains_worker_and_polls_completion(monkeypatch) -> None:
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(dbapi_connection, connection_record) -> None:  # noqa: ANN001
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)

    def override_session():
        session = session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    app = create_app()
    app.dependency_overrides[get_session] = override_session
    client = TestClient(app)
    headers = {"X-Johnny-User-Id": "smoke-user"}

    daily = client.post(
        "/api/v1/agent-runs/daily-recommendation",
        headers=headers,
        json={},
    ).json()["data"]
    training = client.post(
        "/api/v1/agent-runs/training-plan-generation",
        headers=headers,
        json={"plan_type": "base", "starts_on": "2027-01-01"},
    ).json()["data"]

    with session_factory() as session:
        processed = work_drain(session)
        session.commit()

    daily_run = client.get(daily["poll_url"], headers=headers).json()["data"]
    training_run = client.get(training["poll_url"], headers=headers).json()["data"]
    recommendations = client.get("/api/v1/recommendations", headers=headers).json()["data"]
    plans = client.get("/api/v1/training-plans", headers=headers).json()["data"]

    assert processed == 3
    assert daily_run["status"] == "completed"
    assert daily_run["workflow_name"] == "workout_advice"
    assert training_run["status"] == "completed"
    assert len(recommendations) == 0
    assert any(plan["name"] == "Johnny 訓練計畫" and plan["status"] == "active" for plan in plans)


def test_manual_regeneration_produces_race_aware_40km_projection(monkeypatch) -> None:
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)

    def override_session():
        session = session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    app = create_app()
    app.dependency_overrides[get_session] = override_session
    client = TestClient(app)
    today = date.today()
    race_day = today + timedelta(days=98)
    headers = {"X-Johnny-User-Id": "race-aware-runner"}
    with session_factory() as session:
        ensure_current_user(session, CurrentUser(id="race-aware-runner"))
        session.add(TrainingPlanModel(id="previous-race-plan", user_id="race-aware-runner", name="Old Plan", status="active", starts_on=today - timedelta(days=28), ends_on=today + timedelta(days=14), metadata_json={}))
        session.execute(Base.metadata.tables["athlete_profiles"].insert().values(id="race-aware-profile", user_id="race-aware-runner", timezone="UTC", experience_level="intermediate", metadata_json={"current_weekly_mileage_km": 25, "preferred_training_days": ["tuesday", "thursday", "sunday"], "preferred_long_run_day": "sunday", "max_runs_per_week": 3, "max_hard_sessions_per_week": 2}))
        session.add(RaceModel(id="race-40km", user_id="race-aware-runner", name="山徑 40K", race_date=race_day, distance_meters=40_000, status="planned", metadata_json={"priority": "primary", "terrain_difficulty": "technical", "ascent_meters": 1400, "goal_intent": "complete"}))
        completed_end = today - timedelta(days=today.weekday() + 1)
        for week in range(4):
            for run in range(2):
                day = completed_end - timedelta(days=27 - week * 7 - run * 2)
                session.add(ActivityModel(id=f"race-run-{week}-{run}", user_id="race-aware-runner", started_at=datetime.combine(day, datetime.min.time(), tzinfo=timezone.utc) + timedelta(hours=7), activity_type="run", distance_meters=12_500, duration_seconds=4500, provider_summary={}))
        session.commit()

    queued = client.post("/api/v1/training-plans/regenerations", headers=headers, json={"client_request_id": "race-aware-40km", "race_id": "race-40km", "plan_type": "race"})
    assert queued.status_code == 200, queued.text
    with session_factory() as session:
        assert work_drain(session) == 1
        session.commit()
    plans_response = client.get("/api/v1/training-plans", headers=headers)
    assert plans_response.status_code == 200
    plans = plans_response.json()["data"]
    active = next(plan for plan in plans if plan["status"] == "active")
    previous = next(plan for plan in plans if plan["id"] == "previous-race-plan")
    assert previous["status"] == "superseded"
    assert active["metadata"]["workload_policy_version"] == "race-workload-v2"
    assert active["preparation_assessment"]["status"] == "gap"
    assert max(workout["planned_duration_minutes"] for workout in active["workouts"] if workout["workout_type"] == "long_run") > 70
    assert all(workout["steps"] for workout in active["workouts"])
    assert "internal" not in active["metadata"]


def test_invalid_profile_at_worker_time_keeps_previous_projection_active(monkeypatch) -> None:
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)

    def override_session():
        session = session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    app = create_app()
    app.dependency_overrides[get_session] = override_session
    client = TestClient(app)
    today = date.today()
    headers = {"X-Johnny-User-Id": "invalid-profile-runner"}
    with session_factory() as session:
        ensure_current_user(session, CurrentUser(id="invalid-profile-runner"))
        session.add(TrainingPlanModel(id="safe-prior-plan", user_id="invalid-profile-runner", name="Current Plan", status="active", starts_on=today - timedelta(days=14), ends_on=today + timedelta(days=14), metadata_json={}))
        session.execute(Base.metadata.tables["athlete_profiles"].insert().values(id="valid-then-invalid", user_id="invalid-profile-runner", timezone="UTC", experience_level="intermediate", metadata_json={"current_weekly_mileage_km": 25, "max_runs_per_week": 3, "max_hard_sessions_per_week": 2}))
        session.add(RaceModel(id="later-race", user_id="invalid-profile-runner", name="40K", race_date=today + timedelta(days=84), distance_meters=40_000, status="planned", metadata_json={"priority": "primary"}))
        session.commit()

    queued = client.post("/api/v1/training-plans/regenerations", headers=headers, json={"client_request_id": "invalid-after-queue", "race_id": "later-race", "plan_type": "race"})
    assert queued.status_code == 200, queued.text
    with session_factory() as session:
        session.execute(Base.metadata.tables["athlete_profiles"].update().where(Base.metadata.tables["athlete_profiles"].c.id == "valid-then-invalid").values(metadata_json={"current_weekly_mileage_km": 25, "max_runs_per_week": 0}))
        session.commit()
    with session_factory() as session:
        assert work_drain(session) == 1
        session.commit()
    with session_factory() as session:
        active_ids = list(session.scalars(select(TrainingPlanModel.id).where(TrainingPlanModel.user_id == "invalid-profile-runner", TrainingPlanModel.status == "active")))
    assert active_ids == ["safe-prior-plan"]
