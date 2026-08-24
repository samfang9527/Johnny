from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from src.domain.activity_health import CompletedActivity, DailyHealthMetrics


def normalize_garmin_activity(
    *,
    user_id: str,
    provider_connection_id: str,
    payload: dict[str, Any],
) -> CompletedActivity:
    distance = _required_float(payload, "distance")
    duration = _required_int(payload, "duration", fallback_key="elapsedDuration")
    return CompletedActivity.create(
        user_id=user_id,
        source="garmin_connect",
        source_activity_id=str(payload["activityId"]),
        provider_connection_id=provider_connection_id,
        started_at=_parse_garmin_datetime(payload.get("startTimeGMT") or payload.get("startTimeLocal")),
        sport_type=_activity_type(payload["activityType"]),
        distance_meters=distance,
        duration_seconds=duration,
        average_heart_rate=_optional_float(payload.get("averageHR")),
        elevation_gain_meters=_optional_float(payload.get("elevationGain")),
    )


def normalize_garmin_daily_health(*, user_id: str, payload: dict[str, Any]) -> DailyHealthMetrics:
    metric_date = date.fromisoformat(str(payload["calendarDate"]))
    sleep_payload = _as_mapping(payload.get("get_sleep_data"))
    daily_sleep = _as_mapping(sleep_payload.get("dailySleepDTO"))
    sleep_scores = _as_mapping(sleep_payload.get("sleepScores"))
    overall_sleep_score = _as_mapping(sleep_scores.get("overall"))
    hrv_payload = _as_mapping(payload.get("get_hrv_data"))
    hrv_summary = _as_mapping(hrv_payload.get("hrvSummary"))
    rhr_payload = _as_mapping(payload.get("get_rhr_day"))
    stress_payload = _as_mapping(payload.get("get_stress_data"))
    body_battery_payload = _as_mapping(payload.get("get_body_battery"))

    return DailyHealthMetrics.create(
        user_id=user_id,
        source="garmin_connect",
        metric_date=metric_date,
        sleep_duration_minutes=_seconds_to_minutes(
            _first_number(daily_sleep, "sleepTimeSeconds", "durationSeconds")
            or _first_number(sleep_payload, "sleepTimeSeconds", "durationSeconds")
        ),
        sleep_quality=_first_number(overall_sleep_score, "value")
        or _first_number(sleep_payload, "sleepQuality", "overallSleepScore"),
        hrv_ms=_first_number(hrv_summary, "lastNightAvg", "lastNightAverage", "hrvLastNightAverage"),
        hrv_baseline_ms=_first_number(hrv_summary, "weeklyAvg", "baseline", "weeklyAverage"),
        resting_heart_rate=_first_number(rhr_payload, "restingHeartRate", "value"),
        stress_score=_first_number(stress_payload, "avgStressLevel", "stressScore", "value"),
        body_battery_score=_body_battery_score(body_battery_payload),
    )


def _parse_garmin_datetime(value: Any) -> datetime:
    if not value:
        raise ValueError("Garmin activity start time is required")
    text = str(value)
    parsed = datetime.fromisoformat(text.replace("Z", "+00:00") if "T" in text else text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _activity_type(value: Any) -> str:
    if isinstance(value, dict):
        value = value.get("typeKey") or value.get("typeId")
    if not value:
        raise ValueError("Garmin activity type is required")
    return str(value)


def _required_float(payload: dict[str, Any], key: str) -> float:
    value = payload[key]
    return float(value)


def _required_int(payload: dict[str, Any], key: str, *, fallback_key: str | None = None) -> int:
    value = payload.get(key)
    if value is None and fallback_key is not None:
        value = payload.get(fallback_key)
    if value is None:
        raise KeyError(key)
    return int(value)


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


def _as_mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _first_number(payload: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        value = payload.get(key)
        if value is not None:
            return float(value)
    return None


def _seconds_to_minutes(value: float | None) -> float | None:
    if value is None:
        return None
    return value / 60


def _body_battery_score(payload: dict[str, Any]) -> float | None:
    score = _first_number(payload, "charged", "value", "bodyBattery")
    if score is not None:
        return score

    values = payload.get("bodyBatteryValuesArray")
    if not isinstance(values, list):
        return None
    for item in reversed(values):
        if isinstance(item, (list, tuple)) and len(item) >= 2 and item[1] is not None:
            return float(item[1])
    return None
