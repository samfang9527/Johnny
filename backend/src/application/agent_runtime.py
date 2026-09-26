from __future__ import annotations

from contextlib import AbstractContextManager, nullcontext
from dataclasses import replace
from datetime import date, timedelta
from typing import Callable, Iterable

from src.application.training_plan_generation import _template_steps, build_plan_skeleton, projection_window, select_race_strategy
from src.application.training_targets import build_pace_profile_from_payloads
from src.domain.agent_runtime import (
    AgentContextSource,
    AgentRun,
    AgentRunStep,
    ModelRequest,
    ModelResponse,
    SafetyDecision,
)


PRODUCT_RUN_METADATA_KEYS = (
    "race_id",
    "plan_type",
    "starts_on",
    "plan_horizon_weeks",
    "client_request_id",
    "manual_regeneration",
    "quota_day",
    "trigger_type",
    "replace_active_projection",
    "previous_ends_on",
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
        transaction_factory: Callable[[], AbstractContextManager] | None = None,
    ) -> None:
        self._run_store = run_store
        self._model_gateway = model_gateway
        self._tools = tools
        self._prompt_version = prompt_version
        self._provider = provider
        self._model = model
        self._transaction_factory = transaction_factory or nullcontext

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
        requested_plan_type = _canonical_plan_type(plan_type)
        race_strategy = self._select_training_plan_race(
            user_id=user_id,
            explicit_race_id=race_id,
            plan_type=requested_plan_type,
            starts_on=starts_on,
        )
        selected_race_id = race_strategy.race_id
        canonical_plan_type = race_strategy.plan_type
        context = {
            "race_id": race_id,
            "selected_race_id": selected_race_id,
            "starts_on": starts_on.isoformat() if starts_on is not None else None,
            "ends_on": ends_on.isoformat() if ends_on is not None else None,
            "plan_horizon_weeks": plan_horizon_weeks,
            "plan_type": canonical_plan_type,
            "goal_notes": goal_notes,
        }
        context.update(
            self._training_plan_generation_preload_context(
                user_id=user_id,
                selected_race_id=selected_race_id,
                starts_on=starts_on,
                plan_type=canonical_plan_type,
            )
        )
        if existing_run is not None:
            for key in PRODUCT_RUN_METADATA_KEYS:
                if key in existing_run.metadata:
                    context[key] = existing_run.metadata[key]
        context["race_id"] = None if context["plan_type"] == "maintenance" else context["selected_race_id"]
        context["model_repair_pending"] = True
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
                        "Do not create recommendations in this workflow. plan_skeleton owns the plan dates, "
                        "weekly structure, phase segments, and workouts. You must not move workout dates or "
                        "change the weekly structure; call createTrainingPlan using the plan_skeleton dates."
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
    ):
        anchor = starts_on or date.today()
        if plan_type == "maintenance":
            return select_race_strategy((), anchor, explicit_race_id, force_maintenance=True)
        if "getAthleteContext" not in self._tools.names():
            return select_race_strategy((), anchor, explicit_race_id, force_maintenance=False)
        arguments = {"race_id": explicit_race_id} if explicit_race_id else {"race_date_from": anchor.isoformat()}
        payload = self._tools.get("getAthleteContext").run(user_id=user_id, arguments=arguments)
        race_goals = list(payload.get("race_goals", ()))
        return select_race_strategy(race_goals, anchor, explicit_race_id, force_maintenance=False)

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
                transaction = self._transaction_factory if repair_validation_once else nullcontext
                # Roll back a failed generation attempt before logging or repairing it.
                with transaction():
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
                        request_context=request.context,
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
                            request_context=follow_up.context,
                        )

                    if required_error := _required_workflow_output_error(
                        request.workflow_name,
                        training_plan_id=training_plan_id,
                    ):
                        raise ValueError(required_error)
                    output_summary = _run_output_summary(response.content, safety=safety, recommendation_id=recommendation_id)
                    completed_run = run
                    if training_plan_id:
                        completed_run = _with_created_training_plan_id(run, training_plan_id)
                    return self._run_store.complete_run(
                        completed_run.complete(
                            output_summary=output_summary,
                            token_usage=token_usage,
                            recommendation_id=recommendation_id,
                        )
                    )
            except Exception as exc:
                if repair_validation_once:
                    training_plan_id = None
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
                if (
                    repair_validation_once
                    and repair_attempted
                    and isinstance(exc, ValueError)
                    and (
                        str(exc) != "training plan generation did not create a training plan"
                        or isinstance((request.context or {}).get("preserved_generation"), dict)
                    )
                ):
                    fallback = self._run_fallback_training_plan(
                        run=run,
                        request=request,
                        user_id=user_id,
                        sequence_number=sequence_number,
                        token_usage=token_usage,
                    )
                    if fallback is not None:
                        return fallback
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
        request_context: dict | None = None,
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
            if tool_call.tool_name == "createTrainingPlan":
                _inject_training_plan_trusted_context(arguments, request_context or {})
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

    def _training_plan_generation_preload_context(
        self,
        *,
        user_id: str,
        selected_race_id: str | None,
        starts_on: date | None,
        plan_type: str,
    ) -> dict:
        athlete_arguments = (
            {"race_id": selected_race_id}
            if selected_race_id is not None
            else {"race_date_from": (starts_on or date.today()).isoformat()}
        )
        athlete_context = _safe_tool_payload(
            self._tools,
            "getAthleteContext",
            user_id=user_id,
            arguments=athlete_arguments,
        )
        anchor = starts_on or date.today()
        recent_activities = _safe_tool_payload(
            self._tools,
            "getRecentActivities",
            user_id=user_id,
            arguments={
                "start_date": (anchor - timedelta(days=28)).isoformat(),
                "end_date": anchor.isoformat(),
                "limit": 20,
                "offset": 0,
            },
        )
        current_plan_payload = _safe_tool_payload(
            self._tools,
            "getTrainingPlan",
            user_id=user_id,
            arguments={"training_plan_id": None},
        )
        race_goals = list((athlete_context or {}).get("race_goals", ()))
        selected_race = next((goal for goal in race_goals if goal.get("id") == selected_race_id), None)
        effective_selected_race_id = str(selected_race["id"]) if selected_race is not None else None
        activities = tuple((recent_activities or {}).get("activities", ()))
        last_active_plan = (current_plan_payload or {}).get("training_plan")
        pace_profile = build_pace_profile_from_payloads(
            profile_payload=(athlete_context or {}).get("profile"),
            selected_race_payload=selected_race,
            recent_activity_payloads=activities,
        )
        continuity_context = _plan_continuity_context(
            last_active_plan if isinstance(last_active_plan, dict) else None,
            selected_race_id=effective_selected_race_id,
        )
        profile = (athlete_context or {}).get("profile")
        profile_payload = profile if isinstance(profile, dict) else {}
        canonical_plan_type = "race" if plan_type == "race" and selected_race is not None else "maintenance"
        race_date = _goal_date(selected_race) if selected_race is not None else None
        skeleton_starts_on, skeleton_ends_on = projection_window(anchor, race_date, canonical_plan_type)
        skeleton = build_plan_skeleton(
            starts_on=skeleton_starts_on,
            ends_on=skeleton_ends_on,
            plan_type=canonical_plan_type,
            race_date=race_date,
            preferred_training_days=tuple(profile_payload.get("preferred_training_days") or ()),
            preferred_long_run_day=str(profile_payload.get("preferred_long_run_day") or "sunday"),
            max_runs_per_week=_profile_int(profile_payload, "max_runs_per_week", default=3),
            max_hard_sessions_per_week=_profile_int(profile_payload, "max_hard_sessions_per_week", default=2),
            injury_status=str(profile_payload.get("injury_status") or "none"),
            race_distance_meters=selected_race.get("distance_meters") if selected_race else None,
            current_weekly_mileage_km=profile_payload.get("current_weekly_mileage_km"),
            experience_level=profile_payload.get("experience_level"),
        )
        plan_skeleton = _plan_skeleton_payload(skeleton)
        return {
            "athlete_context": athlete_context,
            "selected_race": selected_race,
            "selected_race_id": effective_selected_race_id,
            "recent_activity_summary": _recent_activity_summary(activities),
            "key_activities": list(activities[:3]),
            "last_active_plan": last_active_plan if isinstance(last_active_plan, dict) else None,
            "pace_profile": pace_profile.to_payload(),
            "starts_on": plan_skeleton["starts_on"],
            "ends_on": plan_skeleton["ends_on"],
            "plan_skeleton": plan_skeleton,
            "phase_segments": plan_skeleton["phase_segments"],
            "skeleton_workouts": plan_skeleton["workouts"],
            "plan_type": canonical_plan_type,
            **continuity_context,
        }

    def _run_fallback_training_plan(
        self,
        *,
        run: AgentRun,
        request: ModelRequest,
        user_id: str,
        sequence_number: int,
        token_usage,
    ) -> AgentRun | None:
        if request.workflow_name != "training_plan_generation" or "createTrainingPlan" not in self._tools.names():
            return None
        preserved = (request.context or {}).get("preserved_generation")
        arguments = dict(preserved) if isinstance(preserved, dict) else _fallback_training_plan_arguments(request.context or {})
        if isinstance(preserved, dict):
            # Completion Repair reuses trusted candidate IDs without reparsing model IDs.
            arguments["workouts"] = []
        arguments.setdefault("agent_run_id", run.id)
        fallback_context = {**(request.context or {}), "generation_mode": "fallback"}
        _inject_training_plan_trusted_context(arguments, fallback_context)
        try:
            with self._transaction_factory():
                payload = self._tools.get("createTrainingPlan").run(user_id=user_id, arguments=arguments)
                training_plan_id = _training_plan_id_from_payload(payload)
                if not training_plan_id:
                    raise ValueError("fallback did not create a training plan")
                self._run_store.record_step(
                    AgentRunStep.complete_tool_call(
                        agent_run_id=run.id,
                        sequence_number=sequence_number,
                        tool_name="createTrainingPlan",
                        input_summary=_summary_arguments(arguments),
                        output_summary=_summary_payload(payload),
                        payload=payload,
                    )
                )
                return self._run_store.complete_run(
                    _with_created_training_plan_id(run, training_plan_id).complete(
                        output_summary="Created deterministic fallback training plan.",
                        token_usage=token_usage,
                    )
                )
        except Exception:
            return None


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


def _with_created_training_plan_id(run: AgentRun, training_plan_id: str) -> AgentRun:
    return replace(
        run,
        metadata={**run.metadata, "created_training_plan_id": training_plan_id},
    )


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


def _safe_tool_payload(tools, tool_name: str, *, user_id: str, arguments: dict) -> dict | None:
    if tool_name not in tools.names():
        return None
    try:
        payload = tools.get(tool_name).run(user_id=user_id, arguments=arguments)
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def _recent_activity_summary(activities: tuple[dict, ...]) -> dict:
    run_activities = [activity for activity in activities if float(activity.get("distance_meters") or 0) > 0]
    total_distance = sum(float(activity.get("distance_meters") or 0) for activity in run_activities)
    paces = [float(activity.get("average_pace_seconds_per_km") or 0) for activity in run_activities]
    paces = [pace for pace in paces if pace > 0]
    return {
        "activity_count": len(run_activities),
        "total_distance_meters": round(total_distance),
        "average_pace_seconds_per_km": round(sum(paces) / len(paces), 2) if paces else None,
    }


def _inject_training_plan_trusted_context(arguments: dict, request_context: dict) -> None:
    trusted_context: dict = {}
    arguments["trusted_context"] = trusted_context
    pace_profile = request_context.get("pace_profile")
    if isinstance(pace_profile, dict):
        trusted_context["pace_profile"] = pace_profile
    plan_skeleton = request_context.get("plan_skeleton")
    if isinstance(plan_skeleton, dict):
        trusted_context["plan_skeleton"] = plan_skeleton
        trusted_context["phase_segments"] = plan_skeleton.get("phase_segments", ())
        trusted_context["skeleton_workouts"] = plan_skeleton.get("workouts", ())
    for key in PRODUCT_RUN_METADATA_KEYS:
        if key in request_context:
            trusted_context[key] = request_context.get(key)
    for key in ("plan_series_id", "previous_plan_id", "version", "continuity_summary"):
        if key in request_context:
            trusted_context[key] = request_context.get(key)
    if request_context.get("generation_mode") == "fallback":
        trusted_context["generation_mode"] = "fallback"
    for key in ("model_repair_pending", "preserved_generation", "model_repair_reason"):
        if key in request_context:
            trusted_context[key] = request_context[key]


def _plan_continuity_context(last_active_plan: dict | None, *, selected_race_id: str | None) -> dict:
    strategy_series_id = selected_race_id or "maintenance"
    if last_active_plan is None:
        return {
            "plan_series_id": strategy_series_id,
            "previous_plan_id": None,
            "version": 1,
            "continuity_summary": "Initial generated projection.",
        }
    metadata = last_active_plan.get("metadata") if isinstance(last_active_plan.get("metadata"), dict) else {}
    previous_plan_id = last_active_plan.get("id")
    same_race_strategy = last_active_plan.get("race_id") == selected_race_id
    if same_race_strategy:
        plan_series_id = "maintenance" if selected_race_id is None else metadata.get("plan_series_id") or strategy_series_id
        version = _next_plan_version(metadata)
        continuity_summary = metadata.get("continuity_summary") or f"Continue from {last_active_plan.get('name', 'the previous active plan')}."
    else:
        plan_series_id = strategy_series_id
        version = 1
        continuity_summary = "Generated projection for a new race strategy."
    return {
        "plan_series_id": plan_series_id,
        "previous_plan_id": previous_plan_id,
        "version": version,
        "continuity_summary": continuity_summary,
    }


def _next_plan_version(metadata: dict) -> int:
    raw_version = metadata.get("version")
    if isinstance(raw_version, int):
        return raw_version + 1
    if isinstance(raw_version, str) and raw_version.isdigit():
        return int(raw_version) + 1
    return 2


def _canonical_plan_type(plan_type: str) -> str:
    if plan_type in {"maintenance", "base"}:
        return "maintenance"
    return "race"


def _profile_int(profile: dict, key: str, *, default: int) -> int:
    value = profile.get(key)
    return default if value is None else int(value)


def _plan_skeleton_payload(skeleton) -> dict:
    workouts = [
        {
            "scheduled_for": workout.scheduled_for.isoformat(),
            "workout_type": workout.workout_type,
            "phase": workout.phase,
            "planned_duration_minutes": workout.planned_duration_minutes,
            "planned_distance_meters": workout.planned_distance_meters,
        }
        for workout in skeleton.workouts
    ]
    return {
        "starts_on": skeleton.starts_on.isoformat(),
        "ends_on": skeleton.ends_on.isoformat(),
        "phase_segments": [dict(segment) for segment in skeleton.phase_segments],
        "workouts": workouts,
    }


def _required_plan_skeleton(context: dict) -> dict:
    skeleton = context.get("plan_skeleton")
    if not isinstance(skeleton, dict):
        raise ValueError("plan skeleton is required")
    return skeleton


def _fallback_training_plan_arguments(context: dict) -> dict:
    skeleton = _required_plan_skeleton(context)
    starts_on = _date_from_context(skeleton.get("starts_on"))
    ends_on = _date_from_context(skeleton.get("ends_on"))
    if starts_on is None or ends_on is None:
        raise ValueError("plan skeleton dates are required")
    workouts = [
        _fallback_workout_payload(
            scheduled_for=_date_from_context(workout.get("scheduled_for")) or starts_on,
            workout_type=str(workout["workout_type"]),
            purpose=_fallback_workout_purpose(str(workout["workout_type"])),
            phase=str(workout["phase"]),
            planned_duration_minutes=workout.get("planned_duration_minutes"),
            planned_distance_meters=workout.get("planned_distance_meters"),
            week=(
                ((_date_from_context(workout.get("scheduled_for")) or starts_on) - starts_on).days // 7
            ),
        )
        for workout in skeleton.get("workouts", ())
        if isinstance(workout, dict)
    ]
    return {
        "name": "Fallback Generated Plan",
        "race_id": context.get("selected_race_id"),
        "starts_on": starts_on.isoformat(),
        "ends_on": ends_on.isoformat(),
        "metadata": {
            "plan_series_id": context.get("plan_series_id"),
            "previous_plan_id": context.get("previous_plan_id"),
            "version": context.get("version", 1),
            "generation_mode": "fallback",
            "continuity_summary": "Fallback plan created after generated plan validation failed.",
            "phase_segments": skeleton.get("phase_segments", ()),
        },
        "workouts": workouts,
        "trusted_context": {"generation_mode": "fallback"},
    }


def _fallback_workout_purpose(workout_type: str) -> str:
    return {
        "easy_run": "Aerobic base",
        "interval": "Controlled speed development",
        "hill": "Hill strength development",
        "tempo": "Sustained threshold development",
        "long_run": "Endurance progression",
    }.get(workout_type, "Scheduled training")


def _fallback_workout_payload(
    *,
    scheduled_for: date,
    workout_type: str,
    purpose: str,
    phase: str,
    planned_duration_minutes: int | None,
    planned_distance_meters: int | None,
    week: int,
) -> dict:
    return {
        "scheduled_for": scheduled_for.isoformat(),
        "workout_type": workout_type,
        "purpose": purpose,
        "planned_duration_minutes": planned_duration_minutes,
        "planned_distance_meters": planned_distance_meters,
        "phase": phase,
        "steps": [step.to_payload() for step in _template_steps(workout_type, planned_duration_minutes)],
    }


def _date_from_context(value) -> date | None:
    if isinstance(value, date):
        return value
    if isinstance(value, str) and value:
        return date.fromisoformat(value)
    return None


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
        context={
            **(request.context or {}),
            "model_repair_pending": False,
            "model_repair_reason": str(exc),
            **({"preserved_generation": exc.plan_payload} if hasattr(exc, "plan_payload") else {}),
        },
        require_tool_call=True,
    )
