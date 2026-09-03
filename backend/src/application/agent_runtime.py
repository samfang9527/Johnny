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
TRAINING_PLAN_GENERATION_WRITE_TOOL_NAMES = frozenset({"createTrainingPlan"})


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

    def run_daily_recommendation(
        self,
        *,
        user_id: str,
        anchor_date: date,
        existing_run: AgentRun | None = None,
    ) -> AgentRun:
        run = self._start_run(
            user_id=user_id,
            trigger_type="scheduled",
            workflow_name="daily_recommendation",
            input_summary=f"Daily recommendation for {anchor_date.isoformat()}",
            existing_run=existing_run,
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

    def run_training_plan_generation(
        self,
        *,
        user_id: str,
        race_id: str | None = None,
        starts_on: date | None = None,
        ends_on: date | None = None,
        plan_horizon_weeks: int | None = None,
        plan_type: str = "race",
        goal_notes: str | None = None,
        existing_run: AgentRun | None = None,
    ) -> AgentRun:
        selected_race_id = self._select_training_plan_race(
            user_id=user_id,
            explicit_race_id=race_id,
            plan_type=plan_type,
            starts_on=starts_on,
        )
        context = {
            "race_id": race_id,
            "selected_race_id": selected_race_id,
            "starts_on": starts_on.isoformat() if starts_on is not None else None,
            "ends_on": ends_on.isoformat() if ends_on is not None else None,
            "plan_horizon_weeks": plan_horizon_weeks,
            "plan_type": plan_type,
            "goal_notes": goal_notes,
        }
        run = self._start_run(
            user_id=user_id,
            trigger_type="manual",
            workflow_name="training_plan_generation",
            input_summary="Training plan generation",
            existing_run=existing_run,
        )
        request = ModelRequest(
            user_id=user_id,
            workflow_name="training_plan_generation",
            prompt_version=self._prompt_version,
            messages=(
                {
                    "role": "system",
                    "content": (
                        "Generate a validated active training plan only. Store it with createTrainingPlan. "
                        "Do not create recommendations in this workflow."
                    ),
                },
                {"role": "user", "content": "Create an active running training plan."},
            ),
            tools=_allowed_registered_tools(self._tools.names(), "training_plan_generation"),
            context=context,
            require_tool_call=True,
        )
        return self._run_model_workflow(
            run=run,
            request=request,
            user_id=user_id,
            allowed_tools=set(request.tools),
            repair_validation_once=True,
        )

    def _select_training_plan_race(
        self,
        *,
        user_id: str,
        explicit_race_id: str | None,
        plan_type: str,
        starts_on: date | None,
    ) -> str | None:
        if plan_type == "base":
            return None
        if explicit_race_id:
            return explicit_race_id
        if "getAthleteContext" not in self._tools.names():
            return None
        payload = self._tools.get("getAthleteContext").run(user_id=user_id, arguments={"limit": 20})
        race_goals = list(payload.get("race_goals", ()))
        anchor = starts_on or date.today()
        future_goals = [goal for goal in race_goals if _goal_date(goal) >= anchor]
        primary = [goal for goal in future_goals if goal.get("priority") == "primary"]
        selected = min(primary or future_goals, key=_goal_date, default=None)
        if selected is None:
            return None
        value = selected.get("id")
        return str(value) if value else None

    def _start_run(
        self,
        *,
        user_id: str,
        trigger_type: str,
        workflow_name: str,
        input_summary: str,
        existing_run: AgentRun | None = None,
    ) -> AgentRun:
        if existing_run is not None:
            run = self._run_store.complete_run(existing_run.mark_started())
        else:
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
        repair_validation_once: bool = False,
    ) -> AgentRun:
        sequence_number = len(self._run_store.list_steps_for_run(run.id)) + 1
        recommendation_id: str | None = None
        allowed_tools = set(allowed_tools or request.tools)
        token_usage = None
        repair_attempted = False
        training_plan_id: str | None = None
        while True:
            try:
                response = self._model_gateway.complete(request)
                run = _merge_model_metadata(run, response)
                token_usage = _sum_token_usage(token_usage, response.token_usage)
                tool_results = []
                (
                    recommendation_id,
                    training_plan_id,
                    sequence_number,
                    tool_results,
                ) = self._run_tool_calls(
                    run=run,
                    user_id=user_id,
                    response=response,
                    safety=safety,
                    allowed_tools=allowed_tools,
                    sequence_number=sequence_number,
                    recommendation_id=recommendation_id,
                    training_plan_id=training_plan_id,
                )
                follow_up_tools = _follow_up_write_tools(request.workflow_name, allowed_tools)
                if (
                    _needs_follow_up_write(
                        request.workflow_name,
                        recommendation_id=recommendation_id,
                    )
                    and tool_results
                    and follow_up_tools
                ):
                    follow_up = ModelRequest(
                        user_id=request.user_id,
                        workflow_name=request.workflow_name,
                        prompt_version=request.prompt_version,
                        messages=request.messages
                        + (
                            {
                                "role": "user",
                                "content": (
                                    "Use the Johnny tool results in the structured context to create a pending "
                                    "recommendation now. Call one of the available write tools."
                                ),
                            },
                        ),
                        tools=follow_up_tools,
                        context={**(request.context or {}), "tool_results": tool_results},
                        require_tool_call=True,
                    )
                    response = self._model_gateway.complete(follow_up)
                    run = _merge_model_metadata(run, response)
                    token_usage = _sum_token_usage(token_usage, response.token_usage)
                    (
                        recommendation_id,
                        training_plan_id,
                        sequence_number,
                        _,
                    ) = self._run_tool_calls(
                        run=run,
                        user_id=user_id,
                        response=response,
                        safety=safety,
                        allowed_tools=set(follow_up_tools),
                        sequence_number=sequence_number,
                        recommendation_id=recommendation_id,
                        training_plan_id=training_plan_id,
                    )

                if required_error := _required_workflow_output_error(
                    request.workflow_name,
                    training_plan_id=training_plan_id,
                ):
                    raise ValueError(required_error)
                output_summary = _run_output_summary(response.content, safety=safety, recommendation_id=recommendation_id)
                return self._run_store.complete_run(
                    run.complete(
                        output_summary=output_summary,
                        token_usage=token_usage,
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
                sequence_number += 1
                if repair_validation_once and not repair_attempted and isinstance(exc, ValueError):
                    repair_attempted = True
                    request = _repair_request(request, exc)
                    continue
                return self._run_store.fail_run(
                    run.fail(
                        error_type=exc.__class__.__name__,
                        error_message=str(exc),
                    )
                )

    def _run_tool_calls(
        self,
        *,
        run: AgentRun,
        user_id: str,
        response: ModelResponse,
        safety: SafetyDecision | None,
        allowed_tools: set[str],
        sequence_number: int,
        recommendation_id: str | None,
        training_plan_id: str | None = None,
    ) -> tuple[str | None, str | None, int, list[dict]]:
        tool_results = []
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
            tool_results.append(
                {
                    "tool_name": tool_call.tool_name,
                    "arguments": arguments,
                    "output": payload,
                }
            )
            training_plan_id = _training_plan_id_from_payload(payload) or training_plan_id
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
        return (
            recommendation_id,
            training_plan_id,
            sequence_number,
            tool_results,
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


def _training_plan_id_from_payload(payload: dict) -> str | None:
    plan = payload.get("training_plan")
    if not isinstance(plan, dict):
        return None
    value = plan.get("id")
    return str(value) if value else None


def _required_workflow_output_error(
    workflow_name: str,
    *,
    training_plan_id: str | None,
) -> str | None:
    if workflow_name != "training_plan_generation":
        return None
    if not training_plan_id:
        return "training plan generation did not create a training plan"
    return None


def _needs_follow_up_write(
    workflow_name: str,
    *,
    recommendation_id: str | None,
) -> bool:
    if workflow_name == "training_plan_generation":
        return False
    return recommendation_id is None


def _summary_arguments(arguments: dict) -> str:
    return ", ".join(sorted(arguments.keys()))


def _summary_payload(payload: dict) -> str:
    recommendation_id = _recommendation_id_from_payload(payload)
    if recommendation_id:
        return f"recommendation_id={recommendation_id}"
    return ", ".join(sorted(payload.keys()))


def _run_output_summary(content: str, *, safety: SafetyDecision | None, recommendation_id: str | None) -> str:
    if safety and safety.requires_conservative_response:
        return safety.guidance
    if content:
        return content
    if recommendation_id:
        return f"Created recommendation {recommendation_id}."
    return ""


def _sum_token_usage(left, right):
    if left is None:
        return right
    if right is None:
        return left
    return type(left)(
        input_tokens=_sum_optional_int(left.input_tokens, right.input_tokens),
        output_tokens=_sum_optional_int(left.output_tokens, right.output_tokens),
        total_tokens=_sum_optional_int(left.total_tokens, right.total_tokens),
    )


def _sum_optional_int(left: int | None, right: int | None) -> int | None:
    if left is None and right is None:
        return None
    return (left or 0) + (right or 0)


def _follow_up_write_tools(workflow_name: str, allowed_tools: set[str]) -> tuple[str, ...]:
    if workflow_name == "daily_recommendation":
        candidates = DAILY_WRITE_TOOL_NAMES
    elif workflow_name == "coach_conversation":
        candidates = {"createRecommendation"}
    elif workflow_name == "training_plan_generation":
        candidates = frozenset()
    else:
        candidates = frozenset()
    return tuple(sorted(allowed_tools & candidates))


def _allowed_registered_tools(tool_names: tuple[str, ...], workflow_name: str) -> tuple[str, ...]:
    registered = set(tool_names)
    if workflow_name == "daily_recommendation":
        allowed = READ_TOOL_NAMES | DAILY_WRITE_TOOL_NAMES
    elif workflow_name == "coach_conversation":
        allowed = READ_TOOL_NAMES | CONVERSATION_WRITE_TOOL_NAMES
    elif workflow_name == "training_plan_generation":
        allowed = READ_TOOL_NAMES | TRAINING_PLAN_GENERATION_WRITE_TOOL_NAMES
    else:
        allowed = READ_TOOL_NAMES
    return tuple(sorted(registered & allowed))


def _goal_date(goal: dict) -> date:
    value = goal.get("race_date")
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _repair_request(request: ModelRequest, exc: Exception) -> ModelRequest:
    return ModelRequest(
        user_id=request.user_id,
        workflow_name=request.workflow_name,
        prompt_version=request.prompt_version,
        messages=request.messages
        + (
            {
                "role": "user",
                "content": (
                    "Repair the training plan once using the original request and these validation errors: "
                    f"{exc.__class__.__name__}: {str(exc)}"
                ),
            },
        ),
        tools=request.tools,
        context=request.context,
        require_tool_call=True,
    )
