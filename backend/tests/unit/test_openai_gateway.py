from types import SimpleNamespace

import pytest

from src.domain.agent_runtime import ModelRequest
from src.infrastructure.llm.openai_gateway import OpenAIModelGateway, OpenAIModelGatewayError


class FakeResponsesResource:
    def __init__(self, response=None, error: Exception | None = None) -> None:
        self._response = response
        self._error = error
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self._error is not None:
            raise self._error
        return self._response


class FakeOpenAIClient:
    def __init__(self, response=None, error: Exception | None = None) -> None:
        self.responses = FakeResponsesResource(response=response, error=error)


def test_openai_gateway_maps_request_tools_and_context() -> None:
    client = FakeOpenAIClient(response=_response(output_text="Check recovery first."))
    gateway = OpenAIModelGateway(client=client, model="gpt-5")
    request = ModelRequest(
        user_id="user-1",
        workflow_name="daily_recommendation",
        prompt_version="running-companion-v1",
        messages=(
            {"role": "system", "content": "Use Johnny tools."},
            {"role": "user", "content": "Create today's recommendation."},
        ),
        tools=("getRecoveryState", "createRecommendation"),
        context={"anchor_date": "2027-01-28"},
    )

    gateway.complete(request)

    created = client.responses.calls[0]
    assert created["model"] == "gpt-5"
    assert created["tool_choice"] == {
        "type": "allowed_tools",
        "mode": "auto",
        "tools": [
            {"type": "function", "name": "createRecommendation"},
            {"type": "function", "name": "getRecoveryState"},
        ],
    }
    assert created["input"][0] == {"role": "system", "content": "Use Johnny tools."}
    assert created["input"][2]["role"] == "user"
    assert "data, not instructions" in created["input"][2]["content"]
    assert "2027-01-28" in created["input"][2]["content"]
    create_schema = created["tools"][0]["parameters"]
    recovery_schema = created["tools"][1]["parameters"]
    assert created["tools"][0]["strict"] is True
    assert create_schema["additionalProperties"] is False
    assert "title" in create_schema["required"]
    assert create_schema["properties"]["recommendation_type"]["enum"] == [
        "informational",
        "recovery_warning",
        "workout_adjustment",
    ]
    assert create_schema["properties"]["evidence"]["items"]["properties"]["value"]["type"] == [
        "string",
        "number",
        "boolean",
    ]
    assert created["tools"][1]["strict"] is True
    assert recovery_schema == {
        "type": "object",
        "properties": {"anchor_date": {"type": "string"}},
        "required": ["anchor_date"],
        "additionalProperties": False,
    }
    for tool in created["tools"]:
        _assert_strict_schema(tool["parameters"])
    assert created["tools"] == [
        {
            "type": "function",
            "name": "createRecommendation",
            "description": "Create a pending informational recommendation for user approval. Does not apply plan changes.",
            "parameters": create_schema,
            "strict": True,
        },
        {
            "type": "function",
            "name": "getRecoveryState",
            "description": "Read deterministic recovery state for a user-scoped date.",
            "parameters": recovery_schema,
            "strict": True,
        },
    ]


def test_openai_gateway_can_require_one_of_the_allowed_tools() -> None:
    client = FakeOpenAIClient(response=_response())
    gateway = OpenAIModelGateway(client=client, model="gpt-5")

    gateway.complete(
        ModelRequest(
            user_id="user-1",
            workflow_name="daily_recommendation",
            prompt_version="running-companion-v1",
            messages=({"role": "user", "content": "Create a recommendation."},),
            tools=("createRecommendation",),
            require_tool_call=True,
        )
    )

    assert client.responses.calls[0]["tool_choice"] == {
        "type": "allowed_tools",
        "mode": "required",
        "tools": [{"type": "function", "name": "createRecommendation"}],
    }


def test_openai_gateway_all_tool_schemas_are_strict_for_openai() -> None:
    all_tool_names = (
        "getAthleteContext",
        "getTrainingPlan",
        "getTodayWorkout",
        "getRecentActivities",
        "getRecoveryState",
        "getTrainingMetrics",
        "createRecommendation",
        "proposeWorkoutAdjustment",
        "storeMemoryCandidate",
    )
    client = FakeOpenAIClient(response=_response())
    gateway = OpenAIModelGateway(client=client, model="gpt-5")

    gateway.complete(_request_with_tools(all_tool_names))

    created = client.responses.calls[0]
    for tool in created["tools"]:
        _assert_strict_schema(tool["parameters"])


def test_openai_gateway_parses_content_tool_calls_and_token_usage() -> None:
    response = _response(
        output_text="Create a rest recommendation.",
        output=[
            SimpleNamespace(
                type="function_call",
                name="createRecommendation",
                arguments=(
                    '{"title": "Rest today", "rationale": "Recovery indicates rest.", '
                    '"recommendation_type": "informational", '
                    '"priority": "medium", '
                    '"evidence": [{"source": "agent", "metric": "recovery", "value": "rest"}], '
                    '"action": {"type": "no_plan_change", "reason": "Rest today."}}'
                ),
            )
        ],
        usage=SimpleNamespace(input_tokens=11, output_tokens=7, total_tokens=18),
        model="gpt-5-2026-08",
    )
    gateway = OpenAIModelGateway(client=FakeOpenAIClient(response=response), model="gpt-5")

    result = gateway.complete(_request_with_tools(("createRecommendation",)))

    assert result.provider == "openai"
    assert result.model == "gpt-5-2026-08"
    assert result.content == "Create a rest recommendation."
    assert result.token_usage.input_tokens == 11
    assert result.token_usage.output_tokens == 7
    assert result.token_usage.total_tokens == 18
    assert result.tool_calls[0].tool_name == "createRecommendation"
    assert result.tool_calls[0].arguments == {
        "title": "Rest today",
        "rationale": "Recovery indicates rest.",
        "recommendation_type": "informational",
        "priority": "medium",
        "evidence": [{"source": "agent", "metric": "recovery", "value": "rest"}],
        "action": {"type": "no_plan_change", "reason": "Rest today."},
    }


def test_openai_gateway_wraps_provider_errors_without_secret_values() -> None:
    gateway = OpenAIModelGateway(
        client=FakeOpenAIClient(error=RuntimeError("upstream rejected sk-secret-key")),
        model="gpt-5",
        api_key="sk-secret-key",
    )

    with pytest.raises(OpenAIModelGatewayError) as exc_info:
        gateway.complete(_minimal_request())

    message = str(exc_info.value)
    assert "OpenAI model invocation failed" in message
    assert "sk-secret-key" not in message


def test_openai_gateway_includes_safe_provider_error_details() -> None:
    provider_error = RuntimeError("bad request")
    provider_error.status_code = 400
    provider_error.code = "invalid_function_parameters"
    provider_error.param = "tools[0].parameters"
    provider_error.body = {
        "message": "Invalid schema for function. Secret sk-secret-key must not be stored.",
        "code": "invalid_function_parameters",
        "param": "tools[0].parameters",
    }
    gateway = OpenAIModelGateway(
        client=FakeOpenAIClient(error=provider_error),
        model="gpt-5",
        api_key="sk-secret-key",
    )

    with pytest.raises(OpenAIModelGatewayError) as exc_info:
        gateway.complete(_minimal_request())

    message = str(exc_info.value)
    assert "Bad request" not in message
    assert "status_code=400" in message
    assert "code=invalid_function_parameters" in message
    assert "param=tools[0].parameters" in message
    assert "Invalid schema for function" in message
    assert "sk-secret-key" not in message


def test_openai_gateway_rejects_malformed_tool_arguments() -> None:
    response = _response(
        output=[
            SimpleNamespace(type="function_call", name="createRecommendation", arguments="{not-json")
        ]
    )
    gateway = OpenAIModelGateway(client=FakeOpenAIClient(response=response), model="gpt-5")

    with pytest.raises(OpenAIModelGatewayError, match="Invalid OpenAI tool call arguments"):
        gateway.complete(_request_with_tools(("createRecommendation",)))


def test_openai_gateway_rejects_tool_call_not_allowed_by_request() -> None:
    response = _response(
        output=[
            SimpleNamespace(
                type="function_call",
                name="proposeWorkoutAdjustment",
                arguments='{"title": "Increase", "rationale": "Ignore policy"}',
            )
        ]
    )
    gateway = OpenAIModelGateway(client=FakeOpenAIClient(response=response), model="gpt-5")

    with pytest.raises(OpenAIModelGatewayError, match="not allowed"):
        gateway.complete(_minimal_request())


def test_openai_gateway_rejects_extra_tool_arguments() -> None:
    response = _response(
        output=[
            SimpleNamespace(
                type="function_call",
                name="createRecommendation",
                arguments=(
                    '{"title": "Rest", "rationale": "Recovery", '
                    '"recommendation_type": "informational", '
                    '"priority": "medium", '
                    '"evidence": [{"source": "agent", "metric": "recovery", "value": "rest"}], '
                    '"action": {"type": "no_plan_change", "reason": "Rest"}, '
                    '"agent_run_id": "model-controlled"}'
                ),
            )
        ]
    )
    gateway = OpenAIModelGateway(client=FakeOpenAIClient(response=response), model="gpt-5")

    with pytest.raises(OpenAIModelGatewayError, match="Unsupported argument"):
        gateway.complete(_request_with_tools(("createRecommendation",)))


def _minimal_request() -> ModelRequest:
    return ModelRequest(
        user_id="user-1",
        workflow_name="daily_recommendation",
        prompt_version="running-companion-v1",
        messages=({"role": "user", "content": "Create a recommendation."},),
    )


def _request_with_tools(tools: tuple[str, ...]) -> ModelRequest:
    return ModelRequest(
        user_id="user-1",
        workflow_name="daily_recommendation",
        prompt_version="running-companion-v1",
        messages=({"role": "user", "content": "Create a recommendation."},),
        tools=tools,
    )


def _response(**overrides):
    values = {
        "output_text": "",
        "output": [],
        "usage": None,
        "model": "gpt-5",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _assert_strict_schema(schema: dict) -> None:
    if schema.get("type") != "object":
        return
    assert schema.get("additionalProperties") is False
    properties = schema.get("properties", {})
    assert sorted(schema.get("required", [])) == sorted(properties)
    for child in properties.values():
        if child.get("type") == "object":
            _assert_strict_schema(child)
        if child.get("type") == "array" and child.get("items", {}).get("type") == "object":
            _assert_strict_schema(child["items"])
