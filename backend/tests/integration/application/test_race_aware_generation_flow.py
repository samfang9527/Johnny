from datetime import date

import pytest

from src.api.dependencies import CurrentUser, ensure_current_user
from src.api.routes.training_plans import _plan_response
from src.application.agent_tools import CreateTrainingPlanTool
from src.application.training_plan_generation import PlanRace, build_plan_skeleton
from src.application.training_targets import build_target_profile_from_payloads
from src.infrastructure.database.models import Base, RaceModel
from src.infrastructure.database.training_plan_repository import SqlAlchemyTrainingPlanRepository
from src.infrastructure.llm.local_gateway import _plan_arguments
from src.infrastructure.llm.openai_gateway import _tool_schema


def _skeleton_payload(skeleton):
    return {
        "starts_on": skeleton.starts_on.isoformat(),
        "ends_on": skeleton.ends_on.isoformat(),
        "phase_segments": skeleton.phase_segments,
        "workouts": [
            {
                "scheduled_for": item.scheduled_for.isoformat(),
                "workout_type": item.workout_type,
                "phase": item.phase,
                "planned_duration_minutes": item.planned_duration_minutes,
                "planned_distance_meters": item.planned_distance_meters,
                "race_goal_id": item.race_goal_id,
                "race_name": item.race_name,
                "race_priority": item.race_priority,
                "race_goal_intent": item.race_goal_intent,
                "is_target_race": item.is_target_race,
                "focus_zone": item.focus_zone,
            }
            for item in skeleton.workouts
        ],
    }


@pytest.mark.parametrize("heart_rates", [(55, 190), (None, None)])
def test_local_generation_repair_and_api_preserve_supporting_races_and_target_evidence(
    sqlite_session_factory, heart_rates,
) -> None:
    Base.metadata.create_all(sqlite_session_factory.kw["bind"])
    races = (
        PlanRace("tune", "Park 5K", date(2027, 1, 16), 5_000, "tune_up", False, None),
        PlanRace("secondary", "City 10K", date(2027, 1, 23), 10_000, "secondary", False, None),
        PlanRace("target", "Goal Half", date(2027, 1, 31), 21_097, "primary", True, "perform"),
    )
    skeleton = build_plan_skeleton(
        starts_on=date(2027, 1, 4), ends_on=date(2027, 1, 31), plan_type="race",
        race_date=races[-1].race_date, race_distance_meters=races[-1].distance_meters,
        preferred_training_days=("tuesday", "thursday", "sunday"), preferred_long_run_day="sunday",
        max_runs_per_week=3, max_hard_sessions_per_week=2, current_weekly_mileage_km=35,
        experience_level="intermediate", races=races,
    )
    skeleton_payload = _skeleton_payload(skeleton)
    generated = _plan_arguments({"plan_skeleton": skeleton_payload})
    assert {item["race_goal_id"] for item in generated["workouts"] if item["workout_type"] == "race"} == {"target", "secondary", "tune"}
    assert {"race_goal_id", "race_name", "race_priority"} <= set(_tool_schema("createTrainingPlan")["properties"]["workouts"]["items"]["properties"])

    # A missing tune-up must be restored by deterministic completion repair.
    generated["workouts"] = [item for item in generated["workouts"] if item.get("race_goal_id") != "tune"]
    resting, maximum = heart_rates
    profile = {
        "resting_heart_rate_bpm": resting, "max_heart_rate_bpm": maximum,
        "training_preferences": {"threshold_pace_seconds_per_km": 300},
        "_planning_anchor": "2027-01-04",
    }
    target_profile = build_target_profile_from_payloads(profile, None, (), None)
    with sqlite_session_factory() as session:
        ensure_current_user(session, CurrentUser(id="runner"))
        session.add(RaceModel(id="target", user_id="runner", name="Goal Half", race_date=races[-1].race_date, distance_meters=21_097, status="planned", metadata_json={"priority": "primary"}))
        session.flush()
        repository = SqlAlchemyTrainingPlanRepository(session)
        saved = CreateTrainingPlanTool(training_plans=repository).run(user_id="runner", arguments={
            **generated,
            "trusted_context": {
                "plan_skeleton": skeleton_payload, "target_profile": target_profile.to_payload(),
                "race_id": "target", "plan_type": "race",
            },
        })
        assert saved["completion_repair"]["repaired_week_indexes"]
        plan_id = saved["training_plan"]["id"]
        session.commit()

    with sqlite_session_factory() as session:
        read = SqlAlchemyTrainingPlanRepository(session).get_plan_for_user("runner", plan_id)
        response = _plan_response(read).model_dump(mode="json")
    event_workouts = {item["race_goal_id"]: item for item in response["workouts"] if item["workout_type"] == "race"}
    assert {
        key: (item["scheduled_for"], item["planned_distance_meters"], item["race_priority"])
        for key, item in event_workouts.items()
    } == {
        "tune": ("2027-01-16", 5_000, "tune_up"),
        "secondary": ("2027-01-23", 10_000, "secondary"),
        "target": ("2027-01-31", 21_097, "primary"),
    }
    assert event_workouts["tune"]["steps"][0]["target"]["rpe"] == 6
    assert event_workouts["secondary"]["steps"][0]["target"]["rpe"] == 8
    for event in event_workouts.values():
        target = event["steps"][0]["target"]
        assert target["kind"] == "rpe"
        assert target["pace_source"] == "threshold_pace"
        assert target["pace_range_seconds_per_km"]
    sustained = next(item["steps"][0]["target"] for item in response["workouts"] if item["workout_type"] == "easy_run" and item["steps"])
    assert sustained["kind"] == ("heart_rate" if resting is not None else "rpe")
    assert bool(sustained["heart_rate_range_bpm"]) is (resting is not None)
    assert sustained["pace_source"] == "threshold_pace"
