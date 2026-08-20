from datetime import date, datetime, timezone

from src.application.agent_runtime import FakeModelGateway, RunningCompanionAgent
from src.application.agent_tools import AgentToolRegistry
from src.domain.agent_runtime import AgentContextSource, AgentRun, AgentRunStep, ModelResponse, TokenUsage, ToolCallRequest


class FakeRunStore:
    def __init__(self) -> None:
        self.runs: dict[str, AgentRun] = {}
        self.steps: list[AgentRunStep] = []
        self.sources: list[AgentContextSource] = []
        self.next_id = 1

    def create_run(self, run: AgentRun) -> AgentRun:
        saved = AgentRun.start(
            id=f"run-{self.next_id}",
            user_id=run.user_id,
            trigger_type=run.trigger_type,
            workflow_name=run.workflow_name,
            prompt_version=run.prompt_version,
            provider=run.provider,
            model=run.model,
            input_summary=run.input_summary,
            started_at=datetime(2027, 1, 28, 8, 0, tzinfo=timezone.utc),
        )
        self.next_id += 1
        self.runs[saved.id] = saved
        return saved

    def get_run_for_user(self, user_id: str, run_id: str | None) -> AgentRun | None:
        run = self.runs.get(run_id or "")
        if run is None or run.user_id != user_id:
            return None
        return run

    def record_step(self, step: AgentRunStep) -> AgentRunStep:
        saved = AgentRunStep(
            id=f"step-{len(self.steps) + 1}",
            agent_run_id=step.agent_run_id,
            sequence_number=step.sequence_number,
            step_type=step.step_type,
            name=step.name,
            status=step.status,
            tool_name=step.tool_name,
            input_summary=step.input_summary,
            output_summary=step.output_summary,
            error_type=step.error_type,
            error_message=step.error_message,
            payload=step.payload,
        )
        self.steps.append(saved)
        return saved

    def list_steps_for_run(self, agent_run_id: str) -> list[AgentRunStep]:
        return [step for step in self.steps if step.agent_run_id == agent_run_id]

    def record_context_source(self, source: AgentContextSource) -> AgentContextSource:
        self.sources.append(source)
        return source

    def list_context_sources_for_run(self, agent_run_id: str) -> list[AgentContextSource]:
        return [source for source in self.sources if source.agent_run_id == agent_run_id]

    def complete_run(self, run: AgentRun) -> AgentRun:
        self.runs[run.id] = run
        return run

    def fail_run(self, run: AgentRun) -> AgentRun:
        self.runs[run.id] = run
        return run


class StaticTool:
    def __init__(self, name: str, payload: dict) -> None:
        self.name = name
        self.payload = payload
        self.calls: list[dict] = []

    def run(self, *, user_id: str, arguments: dict) -> dict:
        self.calls.append({"user_id": user_id, "arguments": arguments})
        return self.payload


class FailingTool:
    name = "getRecoveryState"

    def run(self, *, user_id: str, arguments: dict) -> dict:
        raise RuntimeError("tool unavailable")


def test_running_companion_agent_records_daily_recommendation_run_and_tool_steps() -> None:
    run_store = FakeRunStore()
    today_tool = StaticTool(
        "getRecoveryState",
        {
            "recovery": {"readiness_label": "rest"},
            "recommendation": {"id": "recommendation-1", "status": "pending"},
        },
    )
    create_tool = StaticTool(
        "createRecommendation",
        {"recommendation": {"id": "recommendation-1", "status": "pending"}, "applied": False},
    )
    model = FakeModelGateway(
        ModelResponse(
            content="Create a rest recommendation.",
            tool_calls=(
                ToolCallRequest(tool_name="getRecoveryState", arguments={"anchor_date": "2027-01-28"}),
                ToolCallRequest(
                    tool_name="createRecommendation",
                    arguments={
                        "title": "Rest today",
                        "rationale": "Recovery context indicates rest.",
                        "recommendation_type": "informational",
                        "priority": "medium",
                        "evidence": [{"source": "agent", "metric": "readiness_label", "value": "rest"}],
                        "action": {"type": "no_plan_change", "reason": "No safe change."},
                    },
                ),
            ),
            token_usage=TokenUsage(input_tokens=12, output_tokens=8),
            provider="fake",
            model="fake-model",
        )
    )
    agent = RunningCompanionAgent(
        run_store=run_store,
        model_gateway=model,
        tools=AgentToolRegistry((today_tool, create_tool)),
        prompt_version="running-companion-v1",
    )

    result = agent.run_daily_recommendation(user_id="user-1", anchor_date=date(2027, 1, 28))

    assert result.status == "completed"
    assert result.recommendation_id == "recommendation-1"
    assert result.total_tokens == 20
    assert [step.tool_name for step in run_store.steps] == ["getRecoveryState", "createRecommendation"]
    assert run_store.sources[0].source_type == "agent_run_context"
    assert create_tool.calls[0]["arguments"]["agent_run_id"] == "run-1"


def test_running_companion_agent_marks_run_failed_when_tool_errors() -> None:
    run_store = FakeRunStore()
    model = FakeModelGateway(
        ModelResponse(
            content="Use recovery.",
            tool_calls=(ToolCallRequest(tool_name="getRecoveryState", arguments={"anchor_date": "2027-01-28"}),),
        )
    )
    agent = RunningCompanionAgent(
        run_store=run_store,
        model_gateway=model,
        tools=AgentToolRegistry((FailingTool(),)),
        prompt_version="running-companion-v1",
    )

    result = agent.run_daily_recommendation(user_id="user-1", anchor_date=date(2027, 1, 28))

    assert result.status == "failed"
    assert result.error_type == "RuntimeError"
    assert result.recommendation_id is None
    assert run_store.steps[0].status == "failed"


def test_running_companion_agent_blocks_aggressive_change_for_injury_adjacent_prompt() -> None:
    run_store = FakeRunStore()
    aggressive_tool = StaticTool(
        "proposeWorkoutAdjustment",
        {"recommendation": {"id": "unsafe", "status": "pending"}, "applied": False},
    )
    model = FakeModelGateway(
        ModelResponse(
            content="Increase the workout.",
            tool_calls=(
                ToolCallRequest(
                    tool_name="proposeWorkoutAdjustment",
                    arguments={
                        "title": "Increase workout",
                        "rationale": "Push harder.",
                        "before_payload": {"planned_duration_minutes": 30},
                        "after_payload": {"planned_duration_minutes": 90},
                    },
                ),
            ),
        )
    )
    agent = RunningCompanionAgent(
        run_store=run_store,
        model_gateway=model,
        tools=AgentToolRegistry((aggressive_tool,)),
        prompt_version="running-companion-v1",
    )

    result = agent.run_conversation(
        user_id="user-1",
        message="My shin hurts. Should I increase my workout?",
    )

    assert result.status == "completed"
    assert result.recommendation_id is None
    assert aggressive_tool.calls == []
    assert "medical professional" in result.output_summary
    assert run_store.steps[0].step_type == "safety"
