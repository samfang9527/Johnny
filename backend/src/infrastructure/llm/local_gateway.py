from __future__ import annotations

from datetime import date, timedelta

from src.domain.agent_runtime import ModelRequest, ModelResponse, TokenUsage, ToolCallRequest


class LocalCompanionModelGateway:
    """Network-free companion gateway for local development and API tests."""

    def complete(self, request: ModelRequest) -> ModelResponse:
        if request.workflow_name == "daily_recommendation":
            return ModelResponse(
                content="Johnny created a conservative local training recommendation.",
                tool_calls=(
                    ToolCallRequest(
                        tool_name="createRecommendation",
                        arguments=_recommendation_arguments(
                            title="Review today's training context",
                            rationale="Local companion mode reviewed the available context. Connect OpenAI for model-backed analysis.",
                        ),
                    ),
                ),
                token_usage=TokenUsage(input_tokens=0, output_tokens=0, total_tokens=0),
                provider="local",
                model="deterministic-local-companion",
            )

        if request.workflow_name == "training_plan_generation":
            plan_arguments = _plan_arguments(request.context or {})
            return ModelResponse(
                content="Johnny generated a local deterministic active training plan.",
                tool_calls=(
                    ToolCallRequest(
                        tool_name="createTrainingPlan",
                        arguments=plan_arguments,
                    ),
                ),
                token_usage=TokenUsage(input_tokens=0, output_tokens=0, total_tokens=0),
                provider="local",
                model="deterministic-local-companion",
            )

        return ModelResponse(
            content="Johnny received your message in local companion mode. Connect OpenAI for model-backed coaching.",
            tool_calls=(
                ToolCallRequest(
                    tool_name="createRecommendation",
                    arguments=_recommendation_arguments(
                        title="Review today's training context",
                        rationale="Local companion mode created a pending recommendation so the approval loop can be tested end to end.",
                    ),
                ),
            ),
            token_usage=TokenUsage(input_tokens=0, output_tokens=0, total_tokens=0),
            provider="local",
            model="deterministic-local-companion",
        )


def _recommendation_arguments(*, title: str, rationale: str) -> dict:
    return {
        "title": title,
        "rationale": rationale,
        "recommendation_type": "informational",
        "priority": "medium",
        "evidence": [
            {
                "source": "local_companion",
                "metric": "runtime_mode",
                "value": "local",
                "summary": "Network-free local companion mode",
            }
        ],
        "action": {
            "type": "no_plan_change",
            "reason": "Local mode does not apply training changes.",
        },
    }


def _plan_arguments(context: dict) -> dict:
    starts_on = _date_from_context(context.get("starts_on")) or date.today()
    ends_on = starts_on + timedelta(days=27)
    workouts = []
    workout_types = ("easy_run", "strength", "tempo", "long_run")
    for week in range(4):
        week_start = starts_on + timedelta(days=week * 7)
        for offset, workout_type in zip((1, 3, 5, 6), workout_types):
            scheduled_for = week_start + timedelta(days=offset)
            if scheduled_for > ends_on:
                continue
            workouts.append(
                {
                    "scheduled_for": scheduled_for.isoformat(),
                    "workout_type": workout_type,
                    "purpose": _workout_purpose(workout_type),
                    "planned_duration_minutes": 30 + week * 5 + offset * 3,
                }
            )
    return {
        "name": "Local Generated Four Week Plan",
        "race_id": context.get("selected_race_id"),
        "starts_on": starts_on.isoformat(),
        "ends_on": ends_on.isoformat(),
        "workouts": workouts,
    }


def _date_from_context(value) -> date | None:
    if isinstance(value, date):
        return value
    if isinstance(value, str) and value:
        return date.fromisoformat(value)
    return None


def _workout_purpose(workout_type: str) -> str:
    return {
        "easy_run": "Aerobic base",
        "strength": "Durability and injury resistance",
        "tempo": "Sustained threshold development",
        "long_run": "Endurance progression",
    }[workout_type]
