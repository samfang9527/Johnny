from typing import get_type_hints

from src.application.interfaces.agent_runtime import AgentRunStore, AgentTool, AgentToolRegistry, ModelGateway


def test_agent_runtime_interfaces_expose_expected_boundaries() -> None:
    assert "create_run" in AgentRunStore.__dict__
    assert "record_step" in AgentRunStore.__dict__
    assert "record_context_source" in AgentRunStore.__dict__
    assert "complete_run" in AgentRunStore.__dict__
    assert "fail_run" in AgentRunStore.__dict__
    assert "run" in AgentTool.__dict__
    assert "get" in AgentToolRegistry.__dict__
    assert "complete" in ModelGateway.__dict__


def test_model_gateway_contract_accepts_model_request() -> None:
    hints = get_type_hints(ModelGateway.complete)

    assert hints["return"].__name__ == "ModelResponse"
