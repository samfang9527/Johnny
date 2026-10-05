from datetime import date

import pytest

from src.domain.athlete_race import (
    AthletePreferences,
    AthleteProfile,
    DomainValidationError,
    RaceGoal,
    validate_race_goal_date,
)


def test_athlete_profile_can_be_created_and_preferences_updated() -> None:
    profile = AthleteProfile.create(
        user_id="user-1",
        timezone="Asia/Taipei",
        experience_level="intermediate",
        current_weekly_mileage_km=42.5,
        preferred_training_days=("tuesday", "thursday", "sunday"),
        preferred_long_run_day="sunday",
        max_runs_per_week=4,
    )

    updated = profile.with_preferences(
        AthletePreferences(
            preferred_training_days=("monday", "wednesday", "saturday"),
            preferred_long_run_day="saturday",
            max_runs_per_week=3,
            unit_preference="imperial",
            training_preferences={"surface": "trail"},
            injury_status="recent",
            injury_areas=("shin", "quad"),
            injury_notes="Avoid aggressive downhill sessions.",
        )
    )

    assert updated.user_id == "user-1"
    assert updated.timezone == "Asia/Taipei"
    assert updated.current_weekly_mileage_km == 42.5
    assert updated.preferences.preferred_training_days == ("monday", "wednesday", "saturday")
    assert updated.preferences.preferred_long_run_day == "saturday"
    assert updated.preferences.unit_preference == "imperial"
    assert updated.preferences.training_preferences == {"surface": "trail"}
    assert updated.preferences.injury_status == "recent"
    assert updated.preferences.injury_areas == ("shin", "quad")
    assert updated.preferences.injury_notes == "Avoid aggressive downhill sessions."


def test_athlete_profile_allows_unset_experience_and_empty_preferred_days() -> None:
    profile = AthleteProfile.create(
        user_id="user-1",
        timezone="Asia/Taipei",
        experience_level=None,
        current_weekly_mileage_km=0,
        preferred_training_days=(),
        preferred_long_run_day="sunday",
        max_runs_per_week=3,
    )

    assert profile.experience_level is None
    assert profile.preferences.preferred_training_days == ()


def test_athlete_profile_rejects_unknown_experience_level() -> None:
    with pytest.raises(DomainValidationError, match="experience level"):
        AthleteProfile.create(
            user_id="user-1",
            timezone="Asia/Taipei",
            experience_level="unknown",
            current_weekly_mileage_km=0,
            preferred_training_days=("tuesday",),
            preferred_long_run_day="tuesday",
            max_runs_per_week=1,
        )


def test_athlete_profile_rejects_negative_weekly_mileage() -> None:
    with pytest.raises(DomainValidationError, match="weekly mileage"):
        AthleteProfile.create(
            user_id="user-1",
            timezone="Asia/Taipei",
            experience_level="beginner",
            current_weekly_mileage_km=-1,
            preferred_training_days=("tuesday",),
            preferred_long_run_day="tuesday",
            max_runs_per_week=1,
        )


def test_athlete_preferences_allow_run_frequency_below_preferred_days() -> None:
    preferences = AthletePreferences(
        preferred_training_days=("tuesday", "thursday", "sunday"),
        preferred_long_run_day="sunday",
        max_runs_per_week=2,
    )

    assert preferences.max_runs_per_week == 2


def test_athlete_preferences_validate_max_hard_sessions_per_week() -> None:
    default_preferences = AthletePreferences(
        preferred_training_days=("tuesday",),
        preferred_long_run_day="tuesday",
        max_runs_per_week=1,
    )

    assert default_preferences.max_hard_sessions_per_week == 2

    for max_hard_sessions_per_week in (0, 1, 2):
        preferences = AthletePreferences(
            preferred_training_days=("tuesday",),
            preferred_long_run_day="tuesday",
            max_runs_per_week=1,
            max_hard_sessions_per_week=max_hard_sessions_per_week,
        )

        assert preferences.max_hard_sessions_per_week == max_hard_sessions_per_week

    for max_hard_sessions_per_week in (3, -1):
        with pytest.raises(DomainValidationError, match="maximum hard sessions per week must be between 0 and 2"):
            AthletePreferences(
                preferred_training_days=("tuesday",),
                preferred_long_run_day="tuesday",
                max_runs_per_week=1,
                max_hard_sessions_per_week=max_hard_sessions_per_week,
            )


def test_athlete_preferences_reject_duplicate_days_and_long_run_outside_selected_days() -> None:
    with pytest.raises(DomainValidationError, match="unique"):
        AthletePreferences(
            preferred_training_days=("tuesday", " Tuesday "),
            preferred_long_run_day="tuesday",
            max_runs_per_week=2,
        )

    with pytest.raises(DomainValidationError, match="long run day"):
        AthletePreferences(
            preferred_training_days=("tuesday", "thursday"),
            preferred_long_run_day="sunday",
            max_runs_per_week=2,
        )


def test_athlete_preferences_require_notes_for_other_injury_area() -> None:
    with pytest.raises(DomainValidationError, match="other injury"):
        AthletePreferences(
            preferred_training_days=("tuesday",),
            preferred_long_run_day="tuesday",
            max_runs_per_week=1,
            injury_status="current",
            injury_areas=("other",),
        )


def test_race_goal_can_be_created_with_or_without_target_finish_time() -> None:
    with_target = RaceGoal.create(
        user_id="user-1",
        name="Taipei Half Marathon",
        race_date=date(2027, 3, 1),
        distance_meters=21097,
        target_finish_seconds=7200,
        priority="primary",
        status="planned",
    )
    without_target = RaceGoal.create(
        user_id="user-1",
        name="Base 10K",
        race_date=date(2027, 2, 1),
        distance_meters=10_000,
    )

    assert with_target.target_finish_seconds == 7200
    assert with_target.target_pace_seconds_per_km == pytest.approx(341.28, abs=0.01)
    assert without_target.target_finish_seconds is None
    assert without_target.target_pace_seconds_per_km is None


def test_race_goal_accepts_course_demands_and_rejects_invalid_values() -> None:
    race = RaceGoal.create(
        user_id="user-1", name="Mountain 40K", race_date=date(2027, 5, 1),
        distance_meters=40_000, ascent_meters=1800, descent_meters=1750,
        terrain_difficulty="technical", cutoff_seconds=28800, goal_intent="complete",
    )
    assert (race.ascent_meters, race.descent_meters, race.terrain_difficulty) == (1800, 1750, "technical")
    assert (race.cutoff_seconds, race.goal_intent) == (28800, "complete")

    for invalid in ({"ascent_meters": -1}, {"descent_meters": -1},
                    {"cutoff_seconds": 0}, {"terrain_difficulty": "unknown"},
                    {"goal_intent": "win"}):
        with pytest.raises(DomainValidationError):
            RaceGoal.create(
                user_id="user-1", name="Mountain 40K", race_date=date(2027, 5, 1),
                distance_meters=40_000, **invalid,
            )


def test_race_goal_date_validation_rejects_past_dates() -> None:
    race = RaceGoal.create(
        user_id="user-1",
        name="Past 10K",
        race_date=date(2027, 1, 1),
        distance_meters=10_000,
    )

    with pytest.raises(DomainValidationError, match="race date"):
        validate_race_goal_date(race, as_of=date(2027, 1, 2))


def test_race_goal_rejects_non_positive_distance() -> None:
    with pytest.raises(DomainValidationError, match="distance"):
        RaceGoal.create(
            user_id="user-1",
            name="Invalid 10K",
            race_date=date(2027, 3, 1),
            distance_meters=0,
        )


def test_race_goal_derives_target_average_pace() -> None:
    race = RaceGoal.create(
        user_id="user-1",
        name="Marathon",
        race_date=date(2027, 12, 5),
        distance_meters=42_195,
        target_finish_seconds=12_600,
    )

    assert race.target_pace_seconds_per_km == pytest.approx(298.61, abs=0.01)
