from datetime import date, datetime, timezone

from src.application.training_targets import build_pace_profile, enrich_workout_steps
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
