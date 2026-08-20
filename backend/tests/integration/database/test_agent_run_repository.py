from datetime import datetime, timezone

from src.domain.agent_runtime import AgentContextSource, AgentRun, AgentRunStep, TokenUsage
from src.domain.recommendation_approval import EvidenceItem, ProposedAction, Recommendation
from src.infrastructure.database.agent_run_repository import SqlAlchemyAgentRunRepository
from src.infrastructure.database.models import Base, UserModel
from src.infrastructure.database.recommendation_repository import SqlAlchemyRecommendationRepository
from src.infrastructure.database.uow import SqlAlchemyUnitOfWork


def _recommendation(user_id: str, agent_run_id: str) -> Recommendation:
    return Recommendation.create(
        user_id=user_id,
        recommendation_type="informational",
        priority="medium",
        title="Rest today",
        rationale="Recovery evidence indicates rest.",
        evidence=(
            EvidenceItem.create(
                source="agent",
                metric="readiness_label",
                value="rest",
            ),
        ),
        proposed_action=ProposedAction.no_plan_change(reason="No safe workout change."),
        agent_run_id=agent_run_id,
    )


def test_agent_run_repository_creates_completes_fails_and_links_recommendation(sqlite_session_factory) -> None:
    Base.metadata.create_all(sqlite_session_factory.kw["bind"])
    started_at = datetime(2027, 1, 28, 8, 0, tzinfo=timezone.utc)

    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        user = UserModel(email="agent-run@example.com", display_name="Agent Run")
        uow.session.add(user)
        uow.session.flush()
        runs = SqlAlchemyAgentRunRepository(uow.session)
        created = runs.create_run(
            AgentRun.start(
                user_id=user.id,
                trigger_type="scheduled",
                workflow_name="daily_recommendation",
                prompt_version="running-companion-v1",
                provider="fake",
                model="fake-model",
                started_at=started_at,
            )
        )
        recommendation = SqlAlchemyRecommendationRepository(uow.session).create_recommendation(
            user.id,
            _recommendation(user.id, created.id),
        )
        completed = runs.complete_run(
            created.complete(
                finished_at=datetime(2027, 1, 28, 8, 0, 2, tzinfo=timezone.utc),
                output_summary="Created recommendation.",
                token_usage=TokenUsage(input_tokens=20, output_tokens=10),
                recommendation_id=recommendation.id,
            )
        )
        failed = runs.create_run(
            AgentRun.start(
                user_id=user.id,
                trigger_type="manual",
                workflow_name="coach_chat",
                prompt_version="running-companion-v1",
                started_at=started_at,
            )
        )
        failed = runs.fail_run(
            failed.fail(
                finished_at=datetime(2027, 1, 28, 8, 0, 1, tzinfo=timezone.utc),
                error_type="ModelGatewayError",
                error_message="provider unavailable",
            )
        )
        uow.commit()

    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        runs = SqlAlchemyAgentRunRepository(uow.session)
        loaded = runs.get_run_for_user(user.id, completed.id)
        hidden = runs.get_run_for_user("other-user", completed.id)
        failed_loaded = runs.get_run_for_user(user.id, failed.id)

        assert loaded is not None
        assert loaded.status == "completed"
        assert loaded.recommendation_id == recommendation.id
        assert loaded.total_tokens == 30
        assert loaded.latency_ms == 2000
        assert hidden is None
        assert failed_loaded is not None
        assert failed_loaded.status == "failed"
        assert failed_loaded.error_type == "ModelGatewayError"
        assert failed_loaded.recommendation_id is None


def test_agent_run_repository_records_ordered_steps_and_context_sources(sqlite_session_factory) -> None:
    Base.metadata.create_all(sqlite_session_factory.kw["bind"])

    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        user = UserModel(email="agent-steps@example.com", display_name="Agent Steps")
        uow.session.add(user)
        uow.session.flush()
        runs = SqlAlchemyAgentRunRepository(uow.session)
        run = runs.create_run(
            AgentRun.start(
                user_id=user.id,
                trigger_type="scheduled",
                workflow_name="daily_recommendation",
                prompt_version="running-companion-v1",
            )
        )
        later = runs.record_step(
            AgentRunStep.complete_tool_call(
                agent_run_id=run.id,
                sequence_number=2,
                tool_name="createRecommendation",
                input_summary="create recommendation",
                output_summary="recommendation-1",
                payload={"recommendation_id": "recommendation-1"},
            )
        )
        earlier = runs.record_step(
            AgentRunStep.complete_tool_call(
                agent_run_id=run.id,
                sequence_number=1,
                tool_name="getRecoveryState",
                input_summary="get recovery",
                output_summary="readiness=rest",
                payload={"readiness_label": "rest"},
            )
        )
        source = runs.record_context_source(
            AgentContextSource.create(
                agent_run_id=run.id,
                source_type="today_context",
                source_id="2027-01-28",
                source_summary="readiness=rest",
                relevance_score=0.95,
                metadata={"anchor_date": "2027-01-28"},
            )
        )
        uow.commit()

    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        runs = SqlAlchemyAgentRunRepository(uow.session)
        steps = runs.list_steps_for_run(run.id)
        sources = runs.list_context_sources_for_run(run.id)

        assert [step.id for step in steps] == [earlier.id, later.id]
        assert [step.tool_name for step in steps] == ["getRecoveryState", "createRecommendation"]
        assert steps[0].payload["readiness_label"] == "rest"
        assert sources[0].id == source.id
        assert sources[0].metadata["anchor_date"] == "2027-01-28"
