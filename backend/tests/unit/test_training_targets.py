from datetime import date, datetime, timezone

from src.application.training_targets import build_pace_profile, build_target_profile_from_payloads, enrich_workout_steps
from src.domain.activity_health import CompletedActivity
from src.domain.athlete_race import AthleteProfile, RaceGoal
from src.domain.training_plan import WorkoutStep, WorkoutTarget


def _profile(training_preferences: dict | None = None) -> AthleteProfile:
    return AthleteProfile.create(
        user_id="user-1",
        timezone="Asia/Taipei",
        experience_level="intermediate",
        current_weekly_mileage_km=42,
        preferred_training_days=("tuesday", "thursday", "sunday"),
        preferred_long_run_day="sunday",
        max_runs_per_week=5,
        training_preferences=training_preferences or {},
    )


def test_threshold_pace_baseline_builds_high_confidence_pace_profile() -> None:
    profile = build_pace_profile(profile=_profile({"threshold_pace_seconds_per_km": 300}))

    assert profile.confidence == "high"
    assert profile.source == "threshold_pace"
    assert profile.zones["threshold"] == (295, 305)
    assert profile.zones["interval"] == (276, 291)


def test_race_goal_and_activity_baselines_are_low_confidence() -> None:
    race_profile = build_pace_profile(
        profile=_profile(),
        selected_race=RaceGoal.create(
            user_id="user-1",
            name="Taipei 10K",
            race_date=date(2027, 3, 7),
            distance_meters=10_000,
            target_finish_seconds=3_000,
        ),
    )
    activity_profile = build_pace_profile(
        profile=_profile(),
        recent_activities=(
            CompletedActivity.create(
                user_id="user-1",
                source="manual",
                started_at=datetime(2027, 1, 1, 7, 0, tzinfo=timezone.utc),
                sport_type="run",
                distance_meters=5_000,
                duration_seconds=1_600,
            ),
        ),
    )

    assert race_profile.confidence == "low"
    assert race_profile.source == "race_target"
    assert activity_profile.confidence == "low"
    assert activity_profile.source == "recent_activity"


def test_low_confidence_pace_profile_enriches_pace_targets_as_rpe_only() -> None:
    profile = build_pace_profile(
        profile=_profile(),
        selected_race=RaceGoal.create(
            user_id="user-1",
            name="Taipei 10K",
            race_date=date(2027, 3, 7),
            distance_meters=10_000,
            target_finish_seconds=3_000,
        ),
    )

    steps = enrich_workout_steps(
        (
            WorkoutStep.create(
                step_type="work",
                distance_meters=800,
                target=WorkoutTarget.pace(zone="interval", rpe=8),
            ),
        ),
        pace_profile=profile,
    )

    assert steps[0].target is not None
    assert steps[0].target.kind == "rpe"
    assert steps[0].target.rpe == 8


def test_valid_hr_pair_makes_sustained_work_hr_led_with_estimated_pace() -> None:
    profile = build_target_profile_from_payloads(
        profile_payload={"training_preferences": {
            "resting_heart_rate_bpm": 50, "max_heart_rate_bpm": 190,
            "threshold_pace_seconds_per_km": 300,
        }},
        selected_race_payload=None, recent_activity_payloads=(), prior_plan_payload=None,
    )
    steps = enrich_workout_steps(
        (WorkoutStep.create(step_type="free_run", duration_seconds=1800, target=WorkoutTarget.pace(zone="easy", rpe=3)),),
        workout_type="easy_run", target_profile=profile,
    )
    target = steps[0].target
    assert target is not None
    assert target.kind == "heart_rate"
    assert target.heart_rate_range_bpm == (120, 141)
    assert target.pace_range_seconds_per_km == (360, 405)
    assert (target.pace_source, target.confidence) == ("threshold_pace", "high")


def test_missing_hr_uses_rpe_with_goal_derived_pace_for_any_running_target() -> None:
    profile = build_target_profile_from_payloads(
        profile_payload={"current_weekly_mileage_km": 40},
        selected_race_payload={"distance_meters": 10_000, "target_finish_seconds": 3000},
        recent_activity_payloads=(), prior_plan_payload=None,
    )
    steps = enrich_workout_steps(
        (WorkoutStep.create(step_type="work", duration_seconds=1200, target=WorkoutTarget.pace(zone="threshold", pace_range_seconds_per_km=(100, 120), rpe=7)),),
        workout_type="tempo", target_profile=profile,
    )
    target = steps[0].target
    assert target is not None and target.kind == "rpe" and target.rpe == 7
    assert target.pace_source == "goal_time" and target.confidence == "low"
    assert target.pace_range_seconds_per_km is not None
    assert target.pace_range_seconds_per_km[0] > 200


def test_completed_matched_race_beats_goal_time_but_unmatched_run_does_not() -> None:
    prior = {"workouts": [{"id": "race-workout", "workout_type": "race", "status": "completed", "planned_distance_meters": 10_000}]}
    activity = {
        "id": "activity-1", "started_at": "2027-01-20T08:00:00+08:00",
        "matched_workout_id": "race-workout", "distance_meters": 10_100,
        "duration_seconds": 3300, "sport_type": "run",
    }
    goal = {"distance_meters": 10_000, "target_finish_seconds": 3000}
    profile = build_target_profile_from_payloads(
        profile_payload={}, selected_race_payload=goal,
        recent_activity_payloads=(activity,), prior_plan_payload=prior,
    )
    unmatched = build_target_profile_from_payloads(
        profile_payload={}, selected_race_payload=None,
        recent_activity_payloads=({**activity, "matched_workout_id": None},), prior_plan_payload=prior,
    )
    assert (profile.pace_source, profile.pace_confidence) == ("completed_race", "medium")
    assert unmatched.pace_zones == {}


def test_three_paired_flat_easy_runs_can_anchor_provisional_pace() -> None:
    prior = {"workouts": [{"id": f"easy-{index}", "workout_type": "easy_run"} for index in range(3)]}
    activities = tuple({
        "id": f"run-{index}", "started_at": f"2027-01-{20 + index}T08:00:00+08:00",
        "matched_workout_id": f"easy-{index}", "distance_meters": 5_000,
        "duration_seconds": 1800 + index * 30, "average_heart_rate": 125,
        "elevation_gain_meters": 10, "sport_type": "run",
    } for index in range(3))
    profile = build_target_profile_from_payloads(
        profile_payload={"training_preferences": {"resting_heart_rate_bpm": 50, "max_heart_rate_bpm": 190}},
        selected_race_payload=None, recent_activity_payloads=activities, prior_plan_payload=prior,
    )
    assert profile.pace_source == "paired_easy_activities"
    assert profile.pace_confidence == "low"
    assert profile.pace_zones["easy"][0] < 366 < profile.pace_zones["easy"][1]


def test_partial_hr_and_mileage_alone_create_no_numeric_targets() -> None:
    profile = build_target_profile_from_payloads(
        profile_payload={"current_weekly_mileage_km": 50, "training_preferences": {"resting_heart_rate_bpm": 50}},
        selected_race_payload=None, recent_activity_payloads=(), prior_plan_payload=None,
    )
    steps = enrich_workout_steps(
        (WorkoutStep.create(step_type="work", duration_seconds=120, target=WorkoutTarget.pace(zone="interval", rpe=8)),),
        workout_type="interval", target_profile=profile,
    )
    target = steps[0].target
    assert target is not None and target.kind == "rpe"
    assert target.zone == "interval" and target.rpe == 8
    assert target.pace_range_seconds_per_km is None
    assert target.heart_rate_range_bpm is None


def test_controlled_race_uses_rpe_six_zone_even_if_model_suggests_interval() -> None:
    profile = build_target_profile_from_payloads(
        profile_payload={"training_preferences": {
            "resting_heart_rate_bpm": 50, "max_heart_rate_bpm": 190,
            "threshold_pace_seconds_per_km": 300,
        }},
        selected_race_payload=None, recent_activity_payloads=(), prior_plan_payload=None,
    )
    steps = enrich_workout_steps(
        (WorkoutStep.create(step_type="free_run", distance_meters=10_000, target=WorkoutTarget(kind="rpe", zone="interval", rpe=10)),),
        workout_type="race", target_profile=profile, race_rpe=6,
    )
    target = steps[0].target
    assert target is not None and target.kind == "rpe"
    assert target.rpe == 6 and target.zone == "marathon"
    assert target.pace_range_seconds_per_km == (318, 336)
    assert target.heart_rate_range_bpm is None


def test_short_interval_remains_rpe_led_with_valid_hr_pair() -> None:
    profile = build_target_profile_from_payloads(
        profile_payload={"training_preferences": {"resting_heart_rate_bpm": 50, "max_heart_rate_bpm": 190}},
        selected_race_payload=None, recent_activity_payloads=(), prior_plan_payload=None,
    )
    steps = enrich_workout_steps(
        (WorkoutStep.create(step_type="work", duration_seconds=120, target=WorkoutTarget.pace(zone="interval", rpe=8)),),
        workout_type="interval", target_profile=profile,
    )
    assert steps[0].target is not None and steps[0].target.kind == "rpe"
    assert steps[0].target.heart_rate_range_bpm is None
