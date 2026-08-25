from datetime import date, datetime, timezone

import pytest

from src.domain.activity_health import (
    CompletedActivity,
    DailyHealthMetrics,
    DomainValidationError,
    match_activity_to_workout,
)
from src.domain.training_plan import Workout


def _activity(**overrides) -> CompletedActivity:
    values = {
        "user_id": "user-1",
        "source": "manual",
        "started_at": datetime(2027, 1, 3, 7, 30, tzinfo=timezone.utc),
        "sport_type": "run",
        "distance_meters": 10_000,
        "duration_seconds": 3_600,
    }
    values.update(overrides)
    return CompletedActivity.create(**values)


def _workout(*, scheduled_for: date, id: str, status: str = "planned") -> Workout:
    return Workout.create(
        id=id,
        scheduled_for=scheduled_for,
        workout_type="easy_run",
        purpose="Aerobic base",
        planned_duration_minutes=45,
        status=status,
    )


def test_manual_activity_derives_average_pace() -> None:
    activity = _activity(average_heart_rate=145, elevation_gain_meters=120)

    assert activity.source == "manual"
    assert activity.source_activity_id is None
    assert activity.average_pace_seconds_per_km == pytest.approx(360)
    assert activity.average_heart_rate == 145
    assert activity.elevation_gain_meters == 120


def test_provider_activity_requires_and_preserves_source_identity() -> None:
    activity = _activity(
        source="garmin_connect",
        source_activity_id="garmin-activity-1",
        provider_connection_id="connection-1",
    )

    assert activity.source == "garmin_connect"
    assert activity.source_activity_id == "garmin-activity-1"
    assert activity.provider_connection_id == "connection-1"


def test_activity_rejects_invalid_values() -> None:
    with pytest.raises(DomainValidationError, match="distance"):
        _activity(distance_meters=-1)

    with pytest.raises(DomainValidationError, match="duration"):
        _activity(duration_seconds=0)

    with pytest.raises(DomainValidationError, match="source activity id"):
        _activity(source="garmin_connect", source_activity_id=None)

    with pytest.raises(DomainValidationError, match="provider connection"):
        _activity(source="garmin_connect", source_activity_id="activity-1", provider_connection_id=None)


def test_activity_preserves_supplied_average_pace() -> None:
    activity = _activity(average_pace_seconds_per_km=355)

    assert activity.average_pace_seconds_per_km == 355


def test_activity_allows_zero_distance_training_without_positive_pace() -> None:
    activity = _activity(
        source="garmin_connect",
        source_activity_id="garmin-strength-1",
        provider_connection_id="connection-1",
        sport_type="strength_training",
        distance_meters=0,
        duration_seconds=1_800,
    )

    assert activity.distance_meters == 0
    assert activity.duration_seconds == 1_800
    assert activity.average_pace_seconds_per_km == 0


def test_health_metrics_allow_full_and_sparse_daily_entries() -> None:
    full = DailyHealthMetrics.create(
        user_id="user-1",
        metric_date=date(2027, 1, 3),
        source="manual",
        sleep_duration_minutes=480,
        sleep_quality=82,
        hrv_ms=55,
        hrv_baseline_ms=50,
        resting_heart_rate=48,
        stress_score=22,
        body_battery_score=74,
    )
    sparse = DailyHealthMetrics.create(
        user_id="user-1",
        metric_date=date(2027, 1, 4),
        source="manual",
        resting_heart_rate=49,
    )

    assert full.values_by_metric_type()["sleep_duration_minutes"] == 480
    assert full.values_by_metric_type()["hrv_ms"] == 55
    assert full.values_by_metric_type()["body_battery_score"] == 74
    assert sparse.values_by_metric_type() == {"resting_heart_rate": 49}


def test_health_metrics_reject_negative_values() -> None:
    with pytest.raises(DomainValidationError, match="sleep duration"):
        DailyHealthMetrics.create(
            user_id="user-1",
            metric_date=date(2027, 1, 3),
            sleep_duration_minutes=-1,
        )

    with pytest.raises(DomainValidationError, match="stress score"):
        DailyHealthMetrics.create(
            user_id="user-1",
            metric_date=date(2027, 1, 3),
            stress_score=-1,
        )

    with pytest.raises(DomainValidationError, match="Body Battery"):
        DailyHealthMetrics.create(
            user_id="user-1",
            metric_date=date(2027, 1, 3),
            body_battery_score=-1,
        )


def test_activity_matches_single_planned_workout_on_same_date() -> None:
    activity = _activity(started_at=datetime(2027, 1, 3, 7, 30, tzinfo=timezone.utc))
    matched = match_activity_to_workout(
        activity,
        (
            _workout(scheduled_for=date(2027, 1, 3), id="workout-1"),
            _workout(scheduled_for=date(2027, 1, 4), id="workout-2"),
        ),
    )

    assert matched.matched_workout_id == "workout-1"


def test_activity_matching_leaves_no_candidate_or_ambiguous_candidate_unmatched() -> None:
    activity = _activity(started_at=datetime(2027, 1, 3, 7, 30, tzinfo=timezone.utc))

    no_candidate = match_activity_to_workout(activity, (_workout(scheduled_for=date(2027, 1, 4), id="workout-1"),))
    ambiguous = match_activity_to_workout(
        activity,
        (
            _workout(scheduled_for=date(2027, 1, 3), id="workout-1"),
            _workout(scheduled_for=date(2027, 1, 3), id="workout-2"),
        ),
    )

    assert no_candidate.matched_workout_id is None
    assert ambiguous.matched_workout_id is None
