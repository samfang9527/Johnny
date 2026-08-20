from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict, dataclass
from datetime import date, datetime, time, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from requests.exceptions import JSONDecodeError as RequestsJSONDecodeError


SECRET_KEYS = {
    "authorization",
    "cookie",
    "cookies",
    "credential",
    "password",
    "session",
    "session_data",
    "token",
}


@dataclass(frozen=True)
class NormalizedActivity:
    provider_activity_id: str
    started_at: datetime
    activity_type: str
    distance_meters: float | None
    duration_seconds: int | None
    provider_summary: dict[str, Any]


@dataclass(frozen=True)
class NormalizedHealthMetric:
    provider_metric_id: str
    measured_at: datetime
    metric_type: str
    value: float
    unit: str
    provider_summary: dict[str, Any]


@dataclass(frozen=True)
class ProbeSettings:
    session_file: Path | None
    email: str | None
    password: str | None


def load_probe_settings(*, env_file: Path | None = None) -> ProbeSettings:
    load_dotenv(dotenv_path=env_file or _default_env_file(), override=False)
    return ProbeSettings(
        session_file=_optional_path(os.getenv("JOHNNY_GARMINCONNECT_SESSION_FILE")),
        email=os.getenv("JOHNNY_GARMINCONNECT_EMAIL"),
        password=os.getenv("JOHNNY_GARMINCONNECT_PASSWORD"),
    )


def normalize_activity_payload(payload: dict[str, Any]) -> NormalizedActivity:
    provider_activity_id = str(payload["activityId"])
    started_at = _parse_garmin_datetime(payload.get("startTimeGMT") or payload.get("startTimeLocal"))
    activity_type = _activity_type(payload.get("activityType"))
    duration = payload.get("duration") or payload.get("elapsedDuration")

    return NormalizedActivity(
        provider_activity_id=provider_activity_id,
        started_at=started_at,
        activity_type=activity_type,
        distance_meters=_optional_float(payload.get("distance")),
        duration_seconds=int(duration) if duration is not None else None,
        provider_summary=_compact_summary(
            payload,
            {
                "activityId",
                "activityName",
                "activityType",
                "averageHR",
                "maxHR",
                "calories",
                "averageSpeed",
                "aerobicTrainingEffect",
                "anaerobicTrainingEffect",
            },
        ),
    )


def normalize_daily_health_payloads(
    *,
    date_text: str,
    source_payloads: dict[str, Any],
) -> list[NormalizedHealthMetric]:
    measured_at = datetime.combine(date.fromisoformat(date_text), time.min, tzinfo=timezone.utc)
    metrics: list[NormalizedHealthMetric] = []

    _append_metric(
        metrics,
        date_text=date_text,
        measured_at=measured_at,
        source_method="get_rhr_day",
        metric_type="resting_heart_rate",
        value=_first_value(source_payloads.get("get_rhr_day", {}), "restingHeartRate", "value"),
        unit="bpm",
        payload=source_payloads.get("get_rhr_day", {}),
    )
    _append_metric(
        metrics,
        date_text=date_text,
        measured_at=measured_at,
        source_method="get_steps_data",
        metric_type="steps",
        value=_first_value(source_payloads.get("get_steps_data", {}), "totalSteps", "dailySteps"),
        unit="count",
        payload=source_payloads.get("get_steps_data", {}),
    )
    sleep_payload = source_payloads.get("get_sleep_data", {})
    sleep_payload_mapping = _as_mapping(sleep_payload)
    daily_sleep_dto = sleep_payload_mapping.get("dailySleepDTO")
    sleep_dto = daily_sleep_dto if isinstance(daily_sleep_dto, dict) else {}
    _append_metric(
        metrics,
        date_text=date_text,
        measured_at=measured_at,
        source_method="get_sleep_data",
        metric_type="sleep_duration",
        value=_first_value(sleep_payload, "sleepTimeSeconds", "durationSeconds")
        or _first_value(sleep_dto, "sleepTimeSeconds", "durationSeconds"),
        unit="seconds",
        payload=sleep_payload,
    )
    _append_metric(
        metrics,
        date_text=date_text,
        measured_at=measured_at,
        source_method="get_stress_data",
        metric_type="stress",
        value=_first_value(source_payloads.get("get_stress_data", {}), "avgStressLevel", "averageStressLevel"),
        unit="score",
        payload=source_payloads.get("get_stress_data", {}),
    )
    _append_metric(
        metrics,
        date_text=date_text,
        measured_at=measured_at,
        source_method="get_spo2_data",
        metric_type="spo2",
        value=_first_value(source_payloads.get("get_spo2_data", {}), "averageSpO2", "averageSpo2", "avgSpo2"),
        unit="percent",
        payload=source_payloads.get("get_spo2_data", {}),
    )
    return metrics


def extract_garmin_embedded_json(page_html: str, key: str) -> dict[str, Any] | None:
    marker = f"{key} = "
    start = page_html.find(marker)
    if start < 0:
        return None
    json_start = page_html.find("{", start + len(marker))
    if json_start < 0:
        return None

    decoder = json.JSONDecoder()
    try:
        value, _ = decoder.raw_decode(page_html[json_start:])
    except json.JSONDecodeError:
        value, _ = decoder.raw_decode(page_html[json_start:].replace('\\"', '"'))
    return value


def fetch_live_payloads(
    *,
    session_file: Path | None,
    email: str | None,
    password: str | None,
    day: date,
    garmin_class: type | None = None,
) -> dict[str, Any]:
    if garmin_class is None:
        from garminconnect import Garmin as garmin_class

    api = _login(session_file=session_file, email=email, password=password, garmin_class=garmin_class)
    day_text = day.isoformat()
    activities = _call_garmin_api(api.get_activities, "fetching activities", 0, 20)
    latest_activity = activities[0] if activities else None
    health_payloads = {
        "get_rhr_day": _call_garmin_api(api.get_rhr_day, "fetching resting heart rate", day_text),
        "get_steps_data": _call_garmin_api(api.get_steps_data, "fetching steps", day_text),
        "get_sleep_data": _call_garmin_api(api.get_sleep_data, "fetching sleep", day_text),
        "get_stress_data": _call_garmin_api(api.get_stress_data, "fetching stress", day_text),
        "get_spo2_data": _call_garmin_api(api.get_spo2_data, "fetching SpO2", day_text),
    }
    return {
        "activity": normalize_activity_payload(latest_activity) if latest_activity else None,
        "health_metrics": normalize_daily_health_payloads(date_text=day_text, source_payloads=health_payloads),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fetch Garmin Connect data and verify schema-normalized payload shape.")
    parser.add_argument("--date", default=date.today().isoformat(), help="Garmin health date to fetch, in YYYY-MM-DD format.")
    parser.add_argument(
        "--session-file",
        type=Path,
        default=None,
        help="Path to an uncommitted garminconnect token-store JSON file.",
    )
    args = parser.parse_args(argv)

    settings = load_probe_settings()
    session_file = args.session_file or settings.session_file
    payloads = fetch_live_payloads(
        session_file=session_file,
        email=settings.email,
        password=settings.password,
        day=date.fromisoformat(args.date),
    )
    print(json.dumps(_json_safe(payloads), indent=2, sort_keys=True))
    return 0


def _login(*, session_file: Path | None, email: str | None, password: str | None, garmin_class: type) -> Any:
    _patch_garmin_json_parser(garmin_class)
    tokenstore = str(session_file) if session_file else None
    if not tokenstore and (not email or not password):
        raise RuntimeError(
            "Set JOHNNY_GARMINCONNECT_SESSION_FILE or both JOHNNY_GARMINCONNECT_EMAIL and "
            "JOHNNY_GARMINCONNECT_PASSWORD. Credentials are used only for the live probe and are not stored in DB."
        )

    api = garmin_class(email, password)
    try:
        api.login(tokenstore)
    except (json.JSONDecodeError, RequestsJSONDecodeError) as exc:
        raise RuntimeError(
            "Garmin Connect login failed while garminconnect parsed Garmin's response. "
            "This usually means Garmin returned an unexpected login, MFA/challenge, or HTML response instead of JSON. "
            "The probe now delegates token loading and refresh to garminconnect's token-store login flow."
        ) from exc
    return api


def _call_garmin_api(method: Any, action: str, *args: Any) -> Any:
    try:
        return method(*args)
    except (json.JSONDecodeError, RequestsJSONDecodeError) as exc:
        raise RuntimeError(
            f"Garmin Connect returned a non-JSON response while {action}. "
            "This often means the cached token/session is invalid or Garmin returned an HTML login/challenge page. "
            "Delete the local Garmin token-store file and rerun the probe with email/password set in backend/.env."
        ) from exc


def _patch_garmin_json_parser(garmin_class: type) -> None:
    setattr(garmin_class, "_Garmin__get_json", staticmethod(extract_garmin_embedded_json))


def _append_metric(
    metrics: list[NormalizedHealthMetric],
    *,
    date_text: str,
    measured_at: datetime,
    source_method: str,
    metric_type: str,
    value: Any,
    unit: str,
    payload: Any,
) -> None:
    if value is None:
        return
    metrics.append(
        NormalizedHealthMetric(
            provider_metric_id=f"garmin-{metric_type}-{date_text}",
            measured_at=measured_at,
            metric_type=metric_type,
            value=float(value),
            unit=unit,
            provider_summary=_provider_summary(source_method=source_method, payload=payload),
        )
    )


def _first_value(payload: Any, *keys: str) -> Any:
    if isinstance(payload, list):
        for item in payload:
            value = _first_value(item, *keys)
            if value is not None:
                return value
        return None
    if not isinstance(payload, dict):
        return None
    for key in keys:
        value = payload.get(key)
        if value is not None:
            return value
    return None


def _as_mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _provider_summary(*, source_method: str, payload: Any) -> dict[str, Any]:
    redacted_payload = _redact_secrets(payload)
    if isinstance(redacted_payload, dict):
        return {"source_method": source_method, **redacted_payload}
    return {"source_method": source_method, "payload": redacted_payload}


def _activity_type(activity_type: Any) -> str:
    if isinstance(activity_type, dict):
        return str(activity_type.get("typeKey") or activity_type.get("typeId") or "unknown")
    if activity_type is not None:
        return str(activity_type)
    return "unknown"


def _parse_garmin_datetime(value: Any) -> datetime:
    if not isinstance(value, str):
        raise ValueError("Garmin activity payload is missing a start time")
    normalized = value.replace("Z", "+00:00")
    if " " in normalized and "T" not in normalized:
        normalized = normalized.replace(" ", "T")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _optional_float(value: Any) -> float | None:
    return float(value) if value is not None else None


def _compact_summary(payload: dict[str, Any], allowed_keys: set[str]) -> dict[str, Any]:
    return {key: _redact_secrets(value) for key, value in payload.items() if key in allowed_keys}


def _redact_secrets(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _redact_secrets(item) for key, item in value.items() if key.lower() not in SECRET_KEYS}
    if isinstance(value, list):
        return [_redact_secrets(item) for item in value]
    return value


def _json_safe(value: Any) -> Any:
    if hasattr(value, "__dataclass_fields__"):
        return _json_safe(asdict(value))
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    return value


def _optional_path(value: str | None) -> Path | None:
    return Path(value).expanduser() if value else None


def _default_env_file() -> Path:
    return Path(__file__).resolve().parents[3] / ".env"


if __name__ == "__main__":
    raise SystemExit(main())
