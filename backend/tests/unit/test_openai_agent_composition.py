from datetime import date, datetime, timezone
from types import SimpleNamespace

from src.application.agent_tools import AgentToolRegistry
from src.domain.agent_runtime import AgentContextSource, AgentRun, AgentRunStep
from src.infrastructure.llm.composition import build_running_companion_agent
from src.infrastructure.llm.settings import LlmSettings


class FakeRunStore:
    def __init__(self) -> None:
        self.runs: dict[str, AgentRun] = {}
        self.steps: list[AgentRunStep] = []
        self.sources: list[AgentContextSource] = []

    def create_run(self, run: AgentRun) -> AgentRun:
        saved = AgentRun.start(
            id="run-1",
            user_id=run.user_id,
            trigger_type=run.trigger_type,
            workflow_name=run.workflow_name,
            prompt_version=run.prompt_version,
            provider=run.provider,
            model=run.model,
            input_summary=run.input_summary,
            started_at=datetime(2027, 1, 28, 8, 0, tzinfo=timezone.utc),
        )
        self.runs[saved.id] = saved
        return saved

    def get_run_for_user(self, user_id: str, run_id: str | None) -> AgentRun | None:
        return self.runs.get(run_id or "")

    def record_step(self, step: AgentRunStep) -> AgentRunStep:
        self.steps.append(step)
        return step

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
    name = "createRecommendation"

    def run(self, *, user_id: str, arguments: dict) -> dict:
        return {"recommendation": {"id": "recommendation-1", "status": "pending"}, "applied": False}


class FakeResponsesResource:
    def __init__(self, response=None, error: Exception | None = None) -> None:
        self._response = response
        self._error = error

    def create(self, **kwargs):
        if self._error is not None:
            raise self._error
        return self._response


class FakeOpenAIClient:
    def __init__(self, response=None, error: Exception | None = None) -> None:
        self.responses = FakeResponsesResource(response=response, error=error)


def test_build_running_companion_agent_uses_openai_gateway_and_persists_metadata() -> None:
    run_store = FakeRunStore()
    agent = build_running_companion_agent(
        run_store=run_store,
        tools=AgentToolRegistry((StaticTool(),)),
        prompt_version="running-companion-v1",
        settings=LlmSettings(provider="openai", model="gpt-5", api_key="sk-local"),
        openai_client=FakeOpenAIClient(
            response=SimpleNamespace(
                output_text="Create recommendation.",
                output=[
                    SimpleNamespace(
                        type="function_call",
                        name="createRecommendation",
                        arguments=(
                            '{"title": "Rest", "rationale": "Recovery", '
                            '"recommendation_type": "informational", '
                            '"priority": "medium", '
                            '"evidence": [{"source": "agent", "metric": "recovery", "value": "rest"}], '
                            '"action": {"type": "no_plan_change", "reason": "Rest", '
                            '"draft_training_plan_id": null, "summary": null}}'
                        ),
                    )
                ],
                usage=SimpleNamespace(input_tokens=10, output_tokens=6, total_tokens=16),
                model="gpt-5-2026-08",
            )
        ),
    )

    result = agent.run_daily_recommendation(user_id="user-1", anchor_date=date(2027, 1, 28))

    assert result.status == "completed"
    assert result.provider == "openai"
    assert result.model == "gpt-5-2026-08"
    assert result.total_tokens == 16
    assert result.recommendation_id == "recommendation-1"
    assert run_store.steps[0].tool_name == "createRecommendation"


def test_openai_gateway_failure_uses_existing_failed_run_behavior() -> None:
    agent = build_running_companion_agent(
        run_store=FakeRunStore(),
        tools=AgentToolRegistry((StaticTool(),)),
        prompt_version="running-companion-v1",
        settings=LlmSettings(provider="openai", model="gpt-5", api_key="sk-local"),
        openai_client=FakeOpenAIClient(error=RuntimeError("provider is unavailable")),
    )

    result = agent.run_daily_recommendation(user_id="user-1", anchor_date=date(2027, 1, 28))

    assert result.status == "failed"
    assert result.error_type == "OpenAIModelGatewayError"
    assert result.recommendation_id is None
