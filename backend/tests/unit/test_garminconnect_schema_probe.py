from pathlib import Path
import json

import pytest
from requests.exceptions import JSONDecodeError as RequestsJSONDecodeError

from datetime import datetime, timezone

from src.infrastructure.integrations.garminconnect_schema_probe import (
    _login,
    extract_garmin_embedded_json,
    fetch_live_payloads,
    load_probe_settings,
    normalize_activity_payload,
    normalize_daily_health_payloads,
)


class FakeGarminClient:
    def __init__(self, email=None, password=None, **kwargs) -> None:
        self.email = email
        self.password = password
        self.kwargs = kwargs
        self.login_tokenstore = None

    def login(self, tokenstore=None) -> None:
        self.login_tokenstore = tokenstore
        return None


class JsonDecodeFailingGarminClient(FakeGarminClient):
    def login(self, tokenstore=None) -> None:
        raise json.JSONDecodeError("Extra data", '{"a": 1}{"b": 2}', 8)


class GarminPageParsingClient(FakeGarminClient):
    @staticmethod
    def _Garmin__get_json(page_html, key):  # noqa: ANN001
        raise json.JSONDecodeError("Extra data", '{"a": 1}{"b": 2}', 8)

    def login(self, tokenstore=None) -> None:
        page_html = (
            'VIEWER_USERPREFERENCES = {"displayName": "Runner", "measurementSystem": "metric"};\n'
            'VIEWER_SOCIAL_PROFILE = {"fullName": "Runner Name"};'
        )
        self.user_preferences = self._Garmin__get_json(page_html, "VIEWER_USERPREFERENCES")


class ApiJsonDecodeFailingClient(FakeGarminClient):
    def get_activities(self, start=0, limit=20):  # noqa: ANN001
        raise RequestsJSONDecodeError("Expecting value", "", 0)


def test_normalize_activity_payload_maps_garminconnect_fields_without_credentials() -> None:
    activity = normalize_activity_payload(
        {
            "activityId": 987654321,
            "activityName": "Morning Run",
            "activityType": {"typeKey": "running"},
            "startTimeGMT": "2027-01-01 22:30:00",
            "distance": 10025.4,
            "duration": 3661.2,
            "averageHR": 142,
            "session_data": {"cookie": "secret"},
            "password": "secret",
        }
    )

    assert activity.provider_activity_id == "987654321"
    assert activity.started_at == datetime(2027, 1, 1, 22, 30, tzinfo=timezone.utc)
    assert activity.activity_type == "running"
    assert activity.distance_meters == 10025.4
    assert activity.duration_seconds == 3661
    assert activity.provider_summary == {
        "activityId": 987654321,
        "activityName": "Morning Run",
        "activityType": {"typeKey": "running"},
        "averageHR": 142,
    }


def test_normalize_daily_health_payloads_maps_garminconnect_daily_values_without_credentials() -> None:
    metrics = normalize_daily_health_payloads(
        date_text="2027-01-01",
        source_payloads={
            "get_rhr_day": {"restingHeartRate": 47, "password": "secret"},
            "get_steps_data": {"totalSteps": 12345, "session_data": {"cookie": "secret"}},
            "get_sleep_data": {"dailySleepDTO": {"sleepTimeSeconds": 28800}},
        },
    )

    assert [(metric.metric_type, metric.value, metric.unit) for metric in metrics] == [
        ("resting_heart_rate", 47.0, "bpm"),
        ("steps", 12345.0, "count"),
        ("sleep_duration", 28800.0, "seconds"),
    ]
    assert all("password" not in metric.provider_summary for metric in metrics)
    assert all("session_data" not in metric.provider_summary for metric in metrics)


def test_load_probe_settings_reads_dotenv_without_overriding_environment(monkeypatch, tmp_path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "JOHNNY_GARMINCONNECT_EMAIL=dotenv@example.com",
                "JOHNNY_GARMINCONNECT_PASSWORD=dotenv-password",
                "JOHNNY_GARMINCONNECT_SESSION_FILE=/tmp/dotenv-session.json",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.delenv("JOHNNY_GARMINCONNECT_EMAIL", raising=False)
    monkeypatch.delenv("JOHNNY_GARMINCONNECT_PASSWORD", raising=False)
    monkeypatch.setenv("JOHNNY_GARMINCONNECT_SESSION_FILE", "/tmp/env-session.json")

    settings = load_probe_settings(env_file=env_file)

    assert settings.email == "dotenv@example.com"
    assert settings.password == "dotenv-password"
    assert settings.session_file == Path("/tmp/env-session.json")


def test_login_delegates_invalid_tokenstore_to_garminconnect_when_credentials_are_available(tmp_path) -> None:
    session_file = tmp_path / "session.json"
    session_file.write_text('{"old": true}{"extra": true}', encoding="utf-8")

    api = _login(
        session_file=session_file,
        email="runner@example.com",
        password="password",
        garmin_class=FakeGarminClient,
    )

    assert api.email == "runner@example.com"
    assert api.password == "password"
    assert api.login_tokenstore == str(session_file)


def test_login_delegates_invalid_tokenstore_to_garminconnect_when_credentials_are_missing(tmp_path) -> None:
    session_file = tmp_path / "session.json"
    session_file.write_text('{"old": true}{"extra": true}', encoding="utf-8")

    api = _login(
        session_file=session_file,
        email=None,
        password=None,
        garmin_class=FakeGarminClient,
    )

    assert api.email is None
    assert api.password is None
    assert api.login_tokenstore == str(session_file)


def test_login_uses_email_password_when_session_file_is_missing(tmp_path) -> None:
    session_file = tmp_path / "missing-session.json"

    api = _login(
        session_file=session_file,
        email="runner@example.com",
        password="password",
        garmin_class=FakeGarminClient,
    )

    assert api.email == "runner@example.com"
    assert api.password == "password"
    assert api.login_tokenstore == str(session_file)


def test_login_wraps_garminconnect_json_decode_failure_from_password_login(tmp_path) -> None:
    with pytest.raises(RuntimeError, match="Garmin Connect login failed"):
        _login(
            session_file=tmp_path / "missing-session.json",
            email="runner@example.com",
            password="password",
            garmin_class=JsonDecodeFailingGarminClient,
        )


def test_extract_garmin_embedded_json_stops_at_matching_object() -> None:
    page_html = (
        'VIEWER_USERPREFERENCES = {"displayName": "Runner", "measurementSystem": "metric"};\n'
        'VIEWER_SOCIAL_PROFILE = {"fullName": "Runner Name"};'
    )

    user_preferences = extract_garmin_embedded_json(page_html, "VIEWER_USERPREFERENCES")

    assert user_preferences == {"displayName": "Runner", "measurementSystem": "metric"}


def test_login_patches_garminconnect_embedded_json_parser(tmp_path) -> None:
    api = _login(
        session_file=tmp_path / "missing-session.json",
        email="runner@example.com",
        password="password",
        garmin_class=GarminPageParsingClient,
    )

    assert api.user_preferences == {"displayName": "Runner", "measurementSystem": "metric"}


def test_fetch_live_payloads_wraps_non_json_activity_response() -> None:
    with pytest.raises(RuntimeError, match="Garmin Connect returned a non-JSON response while fetching activities"):
        fetch_live_payloads(
            session_file=None,
            email="runner@example.com",
            password="password",
            day=datetime(2027, 1, 1).date(),
            garmin_class=ApiJsonDecodeFailingClient,
        )
