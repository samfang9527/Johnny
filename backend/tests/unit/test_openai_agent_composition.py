from types import SimpleNamespace

from src.domain.agent_runtime import ModelRequest
from src.infrastructure.llm.openai_gateway import OpenAIModelGateway


class FakeResponsesResource:
    def __init__(self) -> None:
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(
            output_text="",
            output=[SimpleNamespace(
                type="function_call", name="composeDailyAdvice",
                arguments=(
                    '{"week_summary":"本週已完成訓練","today_execution":"今天放慢",'
                    '"workout_guide":{"purpose":"有氧","expected_feel":"輕鬆",'
                    '"if_too_hard":"減速","if_too_easy":"保持輕鬆"}}'
                ),
            )],
            usage=None, model="test-model",
        )


def test_daily_advice_openai_request_allows_only_structured_composition() -> None:
    resource = FakeResponsesResource()
    gateway = OpenAIModelGateway(model="test-model", client=SimpleNamespace(responses=resource))
    request = ModelRequest(
        user_id="athlete", workflow_name="daily_recommendation", prompt_version="v1",
        messages=({"role": "user", "content": "Generate advice"},),
        tools=("composeDailyAdvice",), require_tool_call=True,
    )

    response = gateway.complete(request)

    assert [call.tool_name for call in response.tool_calls] == ["composeDailyAdvice"]
    assert [tool["name"] for tool in resource.calls[0]["tools"]] == ["composeDailyAdvice"]
    assert resource.calls[0]["tool_choice"]["mode"] == "required"
