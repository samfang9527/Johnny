from src.domain.agent_runtime import ModelRequest
from src.infrastructure.llm.local_gateway import LocalCompanionModelGateway


def test_local_gateway_generates_training_plan_draft_and_pending_recommendation_tool_calls() -> None:
    gateway = LocalCompanionModelGateway()

    response = gateway.complete(
        ModelRequest(
            user_id="user-1",
            workflow_name="training_plan_generation",
            prompt_version="running-companion-v1",
            messages=({"role": "user", "content": "Generate a plan."},),
            tools=("createDraftTrainingPlan", "createRecommendation"),
            context={"selected_race_id": "race-1", "starts_on": "2027-01-01"},
        )
    )

    draft_call = response.tool_calls[0]
    recommendation_call = response.tool_calls[1]

    assert draft_call.tool_name == "createDraftTrainingPlan"
    assert draft_call.arguments["race_id"] == "race-1"
    assert draft_call.arguments["starts_on"] == "2027-01-01"
    assert draft_call.arguments["ends_on"] == "2027-01-28"
    assert 12 <= len(draft_call.arguments["workouts"]) <= 20
    assert recommendation_call.tool_name == "createRecommendation"
    assert recommendation_call.arguments["recommendation_type"] == "training_plan_creation"
    assert recommendation_call.arguments["action"]["type"] == "create_training_plan"
