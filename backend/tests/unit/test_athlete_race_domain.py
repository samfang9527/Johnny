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
        current_weekly_mileage=42.5,
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
            injury_notes="Avoid aggressive downhill sessions.",
        )
    )

    assert updated.user_id == "user-1"
    assert updated.timezone == "Asia/Taipei"
    assert updated.current_weekly_mileage == 42.5
    assert updated.preferences.preferred_training_days == ("monday", "wednesday", "saturday")
    assert updated.preferences.preferred_long_run_day == "saturday"
    assert updated.preferences.unit_preference == "imperial"
    assert updated.preferences.training_preferences == {"surface": "trail"}
    assert updated.preferences.injury_notes == "Avoid aggressive downhill sessions."


def test_athlete_profile_rejects_negative_weekly_mileage() -> None:
    with pytest.raises(DomainValidationError, match="weekly mileage"):
        AthleteProfile.create(
            user_id="user-1",
            timezone="Asia/Taipei",
            experience_level="beginner",
            current_weekly_mileage=-1,
            preferred_training_days=("tuesday",),
            preferred_long_run_day="tuesday",
            max_runs_per_week=1,
        )


def test_athlete_preferences_reject_run_frequency_below_preferred_days() -> None:
    with pytest.raises(DomainValidationError, match="maximum runs per week"):
        AthletePreferences(
            preferred_training_days=("tuesday", "thursday", "sunday"),
            preferred_long_run_day="sunday",
            max_runs_per_week=2,
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
