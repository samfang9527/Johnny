from __future__ import annotations

from datetime import date
from typing import Iterable

from src.domain.agent_runtime import (
    AgentContextSource,
    AgentRun,
    AgentRunStep,
    ModelRequest,
    ModelResponse,
    SafetyDecision,
)


READ_TOOL_NAMES = frozenset(
    {
        "getAthleteContext",
        "getTrainingPlan",
        "getTodayWorkout",
        "getRecentActivities",
        "getRecoveryState",
        "getTrainingMetrics",
    }
)
DAILY_WRITE_TOOL_NAMES = frozenset({"createRecommendation", "proposeWorkoutAdjustment"})
CONVERSATION_WRITE_TOOL_NAMES = frozenset({"createRecommendation", "storeMemoryCandidate"})


class FakeModelGateway:
    def __init__(self, *responses: ModelResponse) -> None:
        self._responses = list(responses)
        self.requests: list[ModelRequest] = []

    def complete(self, request: ModelRequest) -> ModelResponse:
        self.requests.append(request)
        if not self._responses:
            raise RuntimeError("fake model response queue is empty")
        return self._responses.pop(0)


class RunningCompanionAgent:
    def __init__(
        self,
        *,
        run_store,
        model_gateway,
        tools,
        prompt_version: str,
        provider: str | None = None,
        model: str | None = None,
    ) -> None:
        self._run_store = run_store
        self._model_gateway = model_gateway
        self._tools = tools
        self._prompt_version = prompt_version
        self._provider = provider
        self._model = model

    def run_daily_recommendation(self, *, user_id: str, anchor_date: date) -> AgentRun:
        run = self._start_run(
            user_id=user_id,
            trigger_type="scheduled",
            workflow_name="daily_recommendation",
            input_summary=f"Daily recommendation for {anchor_date.isoformat()}",
        )
        request = ModelRequest(
            user_id=user_id,
            workflow_name="daily_recommendation",
            prompt_version=self._prompt_version,
            messages=(
                {"role": "system", "content": "Use available Johnny tools before creating recommendations."},
                {"role": "user", "content": f"Create today's running recommendation for {anchor_date.isoformat()}."},
            ),
            tools=_allowed_registered_tools(self._tools.names(), "daily_recommendation"),
            context={"anchor_date": anchor_date.isoformat()},
        )
        return self._run_model_workflow(run=run, request=request, user_id=user_id, allowed_tools=set(request.tools))

    def run_conversation(self, *, user_id: str, message: str) -> AgentRun:
        safety = SafetyDecision.classify(message)
        run = self._start_run(
            user_id=user_id,
            trigger_type="manual",
            workflow_name="coach_conversation",
            input_summary=message,
        )
        if safety.requires_conservative_response:
            self._run_store.record_step(
                AgentRunStep(
                    agent_run_id=run.id,
                    sequence_number=1,
                    step_type="safety",
                    name="classifySafety",
                    status="completed",
                    input_summary="conversation safety classification",
                    output_summary=safety.category,
                    payload={
                        "category": safety.category,
                        "blocks_aggressive_training_change": safety.blocks_aggressive_training_change,
                    },
                )
            )
        request = ModelRequest(
            user_id=user_id,
            workflow_name="coach_conversation",
            prompt_version=self._prompt_version,
            messages=(
                {"role": "system", "content": "Use conservative safety boundaries for pain or medical topics."},
                {"role": "user", "content": message},
            ),
            tools=_allowed_registered_tools(self._tools.names(), "coach_conversation"),
            context={"safety": safety.category},
        )
        return self._run_model_workflow(
            run=run,
            request=request,
            user_id=user_id,
            safety=safety,
            allowed_tools=set(request.tools),
        )

    def _start_run(
        self,
        *,
        user_id: str,
        trigger_type: str,
        workflow_name: str,
        input_summary: str,
    ) -> AgentRun:
        run = self._run_store.create_run(
            AgentRun.start(
                user_id=user_id,
                trigger_type=trigger_type,
                workflow_name=workflow_name,
                prompt_version=self._prompt_version,
                provider=self._provider,
                model=self._model,
                input_summary=input_summary,
            )
        )
        self._run_store.record_context_source(
            AgentContextSource.create(
                agent_run_id=run.id,
                source_type="agent_run_context",
                source_id=workflow_name,
                source_summary=input_summary,
            )
        )
        return run

    def _run_model_workflow(
        self,
        *,
        run: AgentRun,
        request: ModelRequest,
        user_id: str,
        safety: SafetyDecision | None = None,
        allowed_tools: set[str] | None = None,
    ) -> AgentRun:
        sequence_number = len(self._run_store.list_steps_for_run(run.id)) + 1
        recommendation_id: str | None = None
        allowed_tools = set(allowed_tools or request.tools)
        try:
            response = self._model_gateway.complete(request)
            run = _merge_model_metadata(run, response)
            for tool_call in response.tool_calls:
                if tool_call.tool_name not in allowed_tools:
                    self._run_store.record_step(
                        AgentRunStep(
                            agent_run_id=run.id,
                            sequence_number=sequence_number,
                            step_type="safety",
                            name="blockUnauthorizedTool",
                            status="completed",
                            input_summary=tool_call.tool_name,
                            output_summary="Tool is not allowed for this workflow.",
                            payload={"blocked_tool": tool_call.tool_name},
                        )
                    )
                    sequence_number += 1
                    continue
                if safety is not None and _blocked_by_safety(safety, tool_call.tool_name, tool_call.arguments):
                    self._run_store.record_step(
                        AgentRunStep(
                            agent_run_id=run.id,
                            sequence_number=sequence_number,
                            step_type="safety",
                            name="blockUnsafeAction",
                            status="completed",
                            input_summary=tool_call.tool_name,
                            output_summary=safety.guidance,
                            payload={"blocked_tool": tool_call.tool_name},
                        )
                    )
                    sequence_number += 1
                    continue

                tool = self._tools.get(tool_call.tool_name)
                arguments = dict(tool_call.arguments)
                arguments.setdefault("agent_run_id", run.id)
                payload = tool.run(user_id=user_id, arguments=arguments)
                recommendation_id = _recommendation_id_from_payload(payload) or recommendation_id
                self._run_store.record_step(
                    AgentRunStep.complete_tool_call(
                        agent_run_id=run.id,
                        sequence_number=sequence_number,
                        tool_name=tool_call.tool_name,
                        input_summary=_summary_arguments(arguments),
                        output_summary=_summary_payload(payload),
                        payload=payload,
                    )
                )
                sequence_number += 1

            output_summary = safety.guidance if safety and safety.requires_conservative_response else response.content
            return self._run_store.complete_run(
                run.complete(
                    output_summary=output_summary,
                    token_usage=response.token_usage,
                    recommendation_id=recommendation_id,
                )
            )
        except Exception as exc:
            self._run_store.record_step(
                AgentRunStep.failed(
                    agent_run_id=run.id,
                    sequence_number=sequence_number,
                    step_type="tool",
                    name=exc.__class__.__name__,
                    error_type=exc.__class__.__name__,
                    error_message=str(exc),
                )
            )
            return self._run_store.fail_run(
                run.fail(
                    error_type=exc.__class__.__name__,
                    error_message=str(exc),
                )
            )


def _merge_model_metadata(run: AgentRun, response: ModelResponse) -> AgentRun:
    provider = response.provider or run.provider
    model = response.model or run.model
    if provider == run.provider and model == run.model:
        return run
    return AgentRun(
        id=run.id,
        user_id=run.user_id,
        trigger_type=run.trigger_type,
        workflow_name=run.workflow_name,
        prompt_version=run.prompt_version,
        status=run.status,
        provider=provider,
        model=model,
        correlation_id=run.correlation_id,
        started_at=run.started_at,
        input_summary=run.input_summary,
        trace_ref=run.trace_ref,
        trace=run.trace,
        metadata=run.metadata,
    )


def _blocked_by_safety(safety: SafetyDecision, tool_name: str, arguments: dict) -> bool:
    if not safety.blocks_aggressive_training_change:
        return False
    if tool_name != "proposeWorkoutAdjustment":
        return False
    before = arguments.get("before_payload", {})
    after = arguments.get("after_payload", {})
    before_duration = before.get("planned_duration_minutes")
    after_duration = after.get("planned_duration_minutes")
    if before_duration is not None and after_duration is not None and after_duration > before_duration:
        return True
    before_distance = before.get("planned_distance_meters")
    after_distance = after.get("planned_distance_meters")
    return before_distance is not None and after_distance is not None and after_distance > before_distance


def _recommendation_id_from_payload(payload: dict) -> str | None:
    recommendation = payload.get("recommendation")
    if not isinstance(recommendation, dict):
        return None
    value = recommendation.get("id")
    return str(value) if value else None


def _summary_arguments(arguments: dict) -> str:
    return ", ".join(sorted(arguments.keys()))


def _summary_payload(payload: dict) -> str:
    recommendation_id = _recommendation_id_from_payload(payload)
    if recommendation_id:
        return f"recommendation_id={recommendation_id}"
    return ", ".join(sorted(payload.keys()))


def _allowed_registered_tools(tool_names: tuple[str, ...], workflow_name: str) -> tuple[str, ...]:
    registered = set(tool_names)
    if workflow_name == "daily_recommendation":
        allowed = READ_TOOL_NAMES | DAILY_WRITE_TOOL_NAMES
    elif workflow_name == "coach_conversation":
        allowed = READ_TOOL_NAMES | CONVERSATION_WRITE_TOOL_NAMES
    else:
        allowed = READ_TOOL_NAMES
    return tuple(sorted(registered & allowed))
