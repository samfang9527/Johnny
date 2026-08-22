from __future__ import annotations

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
