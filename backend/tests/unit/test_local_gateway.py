from src.domain.agent_runtime import ModelRequest
from src.infrastructure.llm.local_gateway import LocalCompanionModelGateway


def test_local_gateway_generates_active_training_plan_tool_call_only() -> None:
    gateway = LocalCompanionModelGateway()
    skeleton = {
        "starts_on": "2027-02-01",
        "ends_on": "2027-12-31",
        "phase_segments": [
            {"phase": "build", "starts_on": "2027-02-01", "ends_on": "2027-02-28"},
            {"phase": "race", "starts_on": "2027-03-01", "ends_on": "2027-12-31"},
        ],
        "workouts": [
            {
                "scheduled_for": "2027-02-02",
                "workout_type": "easy_run",
                "phase": "build",
                "planned_duration_minutes": 45,
                "planned_distance_meters": None,
            },
            {
                "scheduled_for": "2027-02-04",
                "workout_type": "interval",
                "phase": "build",
                "planned_duration_minutes": 45,
                "planned_distance_meters": None,
            },
            {
                "scheduled_for": "2027-02-28",
                "workout_type": "long_run",
                "phase": "build",
                "planned_duration_minutes": 75,
                "planned_distance_meters": None,
            },
            {
                "scheduled_for": "2027-03-04",
                "workout_type": "tempo",
                "phase": "race",
                "planned_duration_minutes": 45,
                "planned_distance_meters": None,
            },
            {
                "scheduled_for": "2027-12-30",
                "workout_type": "tempo",
                "phase": "race",
                "planned_duration_minutes": 45,
                "planned_distance_meters": None,
            },
        ],
    }

    response = gateway.complete(
        ModelRequest(
            user_id="user-1",
            workflow_name="training_plan_generation",
            prompt_version="running-companion-v1",
            messages=({"role": "user", "content": "Generate a plan."},),
            tools=("createTrainingPlan",),
            context={"selected_race_id": "race-1", "plan_skeleton": skeleton},
        )
    )

    plan_call = response.tool_calls[0]

    assert len(response.tool_calls) == 1
    assert plan_call.tool_name == "createTrainingPlan"
    assert plan_call.arguments["race_id"] == "race-1"
    assert plan_call.arguments["starts_on"] == skeleton["starts_on"]
    assert plan_call.arguments["ends_on"] == skeleton["ends_on"]
    assert plan_call.arguments["metadata"]["phase_segments"] == skeleton["phase_segments"]
    assert [
        {
            key: workout.get(key)
            for key in (
                "scheduled_for",
                "workout_type",
                "phase",
                "planned_duration_minutes",
                "planned_distance_meters",
            )
        }
        for workout in plan_call.arguments["workouts"]
    ] == skeleton["workouts"]
    interval = next(workout for workout in plan_call.arguments["workouts"] if workout["workout_type"] == "interval")
    assert interval["steps"][1]["type"] == "repeat"
    assert interval["steps"][1]["repeat_count"] >= 4
    assert interval["steps"][1]["steps"][0]["target"]["zone"] == "interval"
    assert plan_call.arguments["name"] == "Johnny 訓練計畫"
    assert interval["purpose"] == "提升速度與有氧能力"
    assert interval["coach_note"] == "每趟保持穩定，組間以輕鬆慢跑恢復。"
    for workout in plan_call.arguments["workouts"]:
        def seconds(steps):
            return sum((step.get("repeat_count", 1) * seconds(step["steps"]) if step["type"] == "repeat" else step.get("duration_seconds", 0)) for step in steps)
        assert seconds(workout["steps"]) == workout["planned_duration_minutes"] * 60
    for workout in (item for item in plan_call.arguments["workouts"] if item["workout_type"] == "tempo"):
        assert sum(step.get("duration_seconds", 0) for step in workout["steps"]) <= workout["planned_duration_minutes"] * 60
