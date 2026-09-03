from src.domain.agent_runtime import ModelRequest
from src.infrastructure.llm.local_gateway import LocalCompanionModelGateway


def test_local_gateway_generates_active_training_plan_tool_call_only() -> None:
    gateway = LocalCompanionModelGateway()

    response = gateway.complete(
        ModelRequest(
            user_id="user-1",
            workflow_name="training_plan_generation",
            prompt_version="running-companion-v1",
            messages=({"role": "user", "content": "Generate a plan."},),
            tools=("createTrainingPlan",),
            context={"selected_race_id": "race-1", "starts_on": "2027-01-01"},
        )
    )

    plan_call = response.tool_calls[0]

    assert len(response.tool_calls) == 1
    assert plan_call.tool_name == "createTrainingPlan"
    assert plan_call.arguments["race_id"] == "race-1"
    assert plan_call.arguments["starts_on"] == "2027-01-01"
    assert plan_call.arguments["ends_on"] == "2027-01-28"
    assert 12 <= len(plan_call.arguments["workouts"]) <= 20
