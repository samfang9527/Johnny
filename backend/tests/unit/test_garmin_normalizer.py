from datetime import date, datetime, timezone

import pytest

from tests.fixtures.garmin_payloads import GARMIN_ACTIVITY_PAYLOAD, GARMIN_DAILY_HEALTH_PAYLOAD
from src.domain.activity_health import DomainValidationError
from src.infrastructure.integrations.garmin_normalizer import normalize_garmin_activity, normalize_garmin_daily_health


def test_garmin_activity_normalizer_maps_supported_fields_to_completed_activity() -> None:
    activity = normalize_garmin_activity(
        user_id="user-1",
        provider_connection_id="conn-1",
        payload=GARMIN_ACTIVITY_PAYLOAD,
    )

    assert activity.user_id == "user-1"
    assert activity.source == "garmin_connect"
    assert activity.source_activity_id == "987654321"
    assert activity.provider_connection_id == "conn-1"
    assert activity.started_at == datetime(2027, 1, 1, 22, 30, tzinfo=timezone.utc)
    assert activity.sport_type == "running"
    assert activity.distance_meters == 10025.4
    assert activity.duration_seconds == 3661
    assert activity.average_heart_rate == 142
    assert activity.elevation_gain_meters == 84.3
    assert activity.average_pace_seconds_per_km == pytest.approx(365.18, abs=0.01)


def test_garmin_activity_normalizer_accepts_missing_optional_fields() -> None:
    payload = {
        "activityId": "minimal-1",
        "activityType": {"typeKey": "walking"},
        "startTimeGMT": "2027-01-02 01:30:00",
        "distance": 1200,
        "duration": 900,
    }

    activity = normalize_garmin_activity(user_id="user-1", provider_connection_id="conn-1", payload=payload)

    assert activity.average_heart_rate is None
    assert activity.elevation_gain_meters is None


def test_garmin_activity_normalizer_rejects_invalid_required_fields() -> None:
    with pytest.raises((KeyError, ValueError, DomainValidationError)):
        normalize_garmin_activity(
            user_id="user-1",
            provider_connection_id="conn-1",
            payload={"activityId": "bad", "duration": 900, "distance": 1200},
        )


def test_garmin_health_normalizer_maps_supported_daily_metrics_and_ignores_unsupported_fields() -> None:
    metrics = normalize_garmin_daily_health(user_id="user-1", payload=GARMIN_DAILY_HEALTH_PAYLOAD)

    assert metrics.user_id == "user-1"
    assert metrics.source == "garmin_connect"
    assert metrics.metric_date == date(2027, 1, 1)
    assert metrics.values_by_metric_type() == {
        "sleep_duration_minutes": 480.0,
        "sleep_quality": 82.0,
        "hrv_ms": 56.0,
        "hrv_baseline_ms": 52.0,
        "resting_heart_rate": 47.0,
        "stress_score": 21.0,
        "body_battery_score": 67.0,
    }


def test_garmin_health_normalizer_accepts_missing_optional_fields() -> None:
    metrics = normalize_garmin_daily_health(
        user_id="user-1",
        payload={"calendarDate": "2027-01-03", "get_rhr_day": {"restingHeartRate": 50}},
    )

    assert metrics.metric_date == date(2027, 1, 3)
    assert metrics.resting_heart_rate == 50
    assert metrics.hrv_ms is None
    assert metrics.body_battery_score is None


def test_garmin_health_normalizer_rejects_payload_without_supported_metrics() -> None:
    with pytest.raises(DomainValidationError):
        normalize_garmin_daily_health(user_id="user-1", payload={"calendarDate": "2027-01-04", "steps": 10000})
