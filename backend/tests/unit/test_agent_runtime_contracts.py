from datetime import datetime, timezone

import pytest

from src.application.agent_runtime import _plan_races_from_payloads

from src.domain.agent_runtime import (
    AgentContextSource,
    AgentRun,
    AgentRunStep,
    ModelRequest,
    ModelResponse,
    SafetyDecision,
    TokenUsage,
    ToolCallRequest,
)


def test_plan_race_preload_filters_status_and_horizon_without_losing_target() -> None:
    races = _plan_races_from_payloads(
        [
            {"id": "target", "name": "Goal", "race_date": "2027-06-01", "distance_meters": 42_195, "priority": "primary", "status": "planned"},
            {"id": "support", "name": "Support", "race_date": "2027-01-10", "distance_meters": 10_000, "priority": "secondary", "status": "active"},
            {"id": "cancelled", "name": "No", "race_date": "2027-01-12", "distance_meters": 5_000, "priority": "tune_up", "status": "cancelled"},
            {"id": "done", "name": "Past", "race_date": "2027-01-14", "distance_meters": 5_000, "priority": "tune_up", "status": "completed"},
        ],
        starts_on=datetime(2027, 1, 1).date(),
        ends_on=datetime(2027, 1, 31).date(),
        selected_race_id="target",
    )

    assert [(race.race_goal_id, race.is_target) for race in races] == [("support", False)]


def test_agent_run_requires_trusted_user_and_prompt_version() -> None:
    with pytest.raises(ValueError, match="user id is required"):
        AgentRun.start(user_id="", trigger_type="scheduled", workflow_name="daily", prompt_version="agent-v1")

    with pytest.raises(ValueError, match="prompt version is required"):
        AgentRun.start(user_id="user-1", trigger_type="scheduled", workflow_name="daily", prompt_version="")


def test_agent_run_records_completion_failure_and_recommendation_link() -> None:
    started_at = datetime(2027, 1, 28, 8, 0, tzinfo=timezone.utc)
    run = AgentRun.start(
        id="run-1",
        user_id="user-1",
        trigger_type="scheduled",
        workflow_name="daily_recommendation",
        prompt_version="running-companion-v1",
        provider="fake",
        model="fake-model",
        started_at=started_at,
    )

    completed = run.complete(
        finished_at=datetime(2027, 1, 28, 8, 0, 1, tzinfo=timezone.utc),
        output_summary="Created recovery recommendation.",
        token_usage=TokenUsage(input_tokens=10, output_tokens=20),
        recommendation_id="recommendation-1",
    )
    failed = run.fail(
        finished_at=datetime(2027, 1, 28, 8, 0, 1, tzinfo=timezone.utc),
        error_type="ModelGatewayError",
        error_message="provider unavailable with a long diagnostic",
    )

    assert completed.status == "completed"
    assert completed.latency_ms == 1000
    assert completed.total_tokens == 30
    assert completed.recommendation_id == "recommendation-1"
    assert failed.status == "failed"
    assert failed.error_type == "ModelGatewayError"
    assert failed.error_message == "provider unavailable with a long diagnostic"
    assert failed.recommendation_id is None


def test_agent_run_can_be_queued_before_worker_start() -> None:
    queued = AgentRun.queue(
        id="run-1",
        user_id="user-1",
        trigger_type="manual",
        workflow_name="daily_recommendation",
        prompt_version="running-companion-v1",
    )

    started = queued.mark_started(started_at=datetime(2027, 1, 28, 8, 0, tzinfo=timezone.utc))

    assert queued.status == "queued"
    assert queued.started_at is None
    assert started.status == "started"
    assert started.started_at == datetime(2027, 1, 28, 8, 0, tzinfo=timezone.utc)


def test_tool_step_and_context_source_serialize_safe_summaries() -> None:
    step = AgentRunStep.complete_tool_call(
        agent_run_id="run-1",
        sequence_number=2,
        tool_name="getRecoveryState",
        input_summary="full recovery context request",
        output_summary="readiness=rest",
        payload={"raw": "not persisted beyond explicit payload"},
        latency_ms=12,
    )
    source = AgentContextSource.create(
        agent_run_id="run-1",
        source_type="today_context",
        source_id="2027-01-28",
        source_summary="recovery rest, one workout scheduled",
        relevance_score=0.9,
    )

    assert step.step_type == "tool"
    assert step.status == "completed"
    assert step.name == "getRecoveryState"
    assert step.tool_name == "getRecoveryState"
    assert step.payload["raw"] == "not persisted beyond explicit payload"
    assert source.metadata == {}
    assert source.relevance_score == 0.9


def test_model_contracts_use_structured_tool_calls_and_token_usage() -> None:
    request = ModelRequest(
        user_id="user-1",
        workflow_name="daily_recommendation",
        prompt_version="running-companion-v1",
        messages=({"role": "system", "content": "Use tools."},),
        tools=("createRecommendation",),
    )
    response = ModelResponse(
        content="Create a recovery recommendation.",
        tool_calls=(
            ToolCallRequest(
                tool_name="createRecommendation",
                arguments={"title": "Rest today"},
            ),
        ),
        token_usage=TokenUsage(input_tokens=7, output_tokens=11),
    )

    assert request.to_payload()["tools"] == ["createRecommendation"]
    assert response.to_payload()["tool_calls"][0]["tool_name"] == "createRecommendation"
    assert response.token_usage.total_tokens == 18


def test_safety_decision_classifies_medical_or_injury_adjacent_text() -> None:
    safe = SafetyDecision.classify("Can I run easy today?")
    unsafe = SafetyDecision.classify("My shin hurts and I have chest pain during running.")

    assert safe.requires_conservative_response is False
    assert unsafe.requires_conservative_response is True
    assert unsafe.blocks_aggressive_training_change is True
    assert "medical professional" in unsafe.guidance
