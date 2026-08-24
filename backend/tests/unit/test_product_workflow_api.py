def test_today_route_returns_context_with_sparse_and_complete_data() -> None:
    from tests.unit.api_test_helpers import create_sqlite_test_client

    client = create_sqlite_test_client()
    sparse = client.get("/api/v1/today?anchor_date=2027-01-02", headers={"X-Johnny-User-Id": "user-1"})
    client.post(
        "/api/v1/races",
        headers={"X-Johnny-User-Id": "user-1"},
        json={"name": "Goal Race", "race_date": "2027-03-01", "distance_meters": 21097},
    )
    client.post(
        "/api/v1/recommendations",
        headers={"X-Johnny-User-Id": "user-1"},
        json={
            "recommendation_type": "informational",
            "priority": "medium",
            "title": "Sleep earlier",
            "rationale": "Sleep debt is high.",
            "evidence": [{"source": "training_analytics", "metric": "sleep_debt", "value": 90}],
            "proposed_action": {"type": "no_plan_change", "reason": "Informational only"},
        },
    )
    client.post(
        "/api/v1/training-plans",
        headers={"X-Johnny-User-Id": "user-1"},
        json={
            "name": "Build",
            "starts_on": "2027-01-01",
            "ends_on": "2027-01-31",
            "workouts": [
                {
                    "scheduled_for": "2027-01-02",
                    "workout_type": "easy_run",
                    "purpose": "Aerobic base",
                    "planned_duration_minutes": 45,
                }
            ],
        },
    )
    complete = client.get("/api/v1/today?anchor_date=2027-01-02", headers={"X-Johnny-User-Id": "user-1"})

    assert sparse.status_code == 200
    assert sparse.json()["data"]["scheduled_workouts"] == []
    assert complete.status_code == 200
    assert complete.json()["data"]["next_race"]["name"] == "Goal Race"
    assert complete.json()["data"]["current_recommendation"]["title"] == "Sleep earlier"
    assert complete.json()["data"]["scheduled_workouts"][0]["purpose"] == "Aerobic base"


def test_recommendation_routes_list_accept_reject_edit_and_discuss() -> None:
    from tests.unit.api_test_helpers import create_sqlite_test_client

    client = create_sqlite_test_client()
    created = client.post(
        "/api/v1/recommendations",
        headers={"X-Johnny-User-Id": "user-1"},
        json={
            "recommendation_type": "informational",
            "priority": "medium",
            "title": "Sleep earlier",
            "rationale": "Sleep debt is high.",
            "evidence": [{"source": "training_analytics", "metric": "sleep_debt", "value": 90}],
            "proposed_action": {"type": "no_plan_change", "reason": "Informational only"},
        },
    ).json()["data"]
    listed = client.get("/api/v1/recommendations", headers={"X-Johnny-User-Id": "user-1"})
    accepted = client.post(f"/api/v1/recommendations/{created['id']}/accept", headers={"X-Johnny-User-Id": "user-1"})

    rejected_source = client.post(
        "/api/v1/recommendations",
        headers={"X-Johnny-User-Id": "user-1"},
        json={
            "recommendation_type": "informational",
            "priority": "low",
            "title": "Hydrate",
            "rationale": "Warm weather.",
            "evidence": [{"source": "weather", "metric": "heat", "value": "warm"}],
            "proposed_action": {"type": "no_plan_change", "reason": "Informational only"},
        },
    ).json()["data"]
    rejected = client.post(f"/api/v1/recommendations/{rejected_source['id']}/reject", headers={"X-Johnny-User-Id": "user-1"})
    edit_source = client.post(
        "/api/v1/recommendations",
        headers={"X-Johnny-User-Id": "user-1"},
        json={
            "recommendation_type": "informational",
            "priority": "medium",
            "title": "Fuel earlier",
            "rationale": "Workout is early.",
            "evidence": [{"source": "calendar", "metric": "start_time", "value": "early"}],
            "proposed_action": {"type": "no_plan_change", "reason": "Informational only"},
        },
    ).json()["data"]
    edited = client.post(
        f"/api/v1/recommendations/{edit_source['id']}/edit",
        headers={"X-Johnny-User-Id": "user-1"},
        json={"type": "no_plan_change", "reason": "User prefers no change"},
    )
    discussed = client.post(
        f"/api/v1/recommendations/{rejected_source['id']}/discuss",
        headers={"X-Johnny-User-Id": "user-1"},
        json={"content": "Why this recommendation?"},
    )

    assert listed.status_code == 200
    assert listed.json()["data"][0]["evidence"][0]["metric"] == "sleep_debt"
    assert accepted.json()["data"]["decision"] == "accepted"
    assert rejected.json()["data"]["decision"] == "rejected"
    assert edited.status_code == 200
    assert edited.json()["data"]["status"] == "pending"
    assert edited.json()["data"]["proposed_action"]["reason"] == "User prefers no change"
    assert discussed.status_code == 200
    assert discussed.json()["data"]["message"]["content"] == "Why this recommendation?"


def test_conversation_route_rejects_empty_and_returns_run_reference() -> None:
    from tests.unit.api_test_helpers import create_sqlite_test_client

    client = create_sqlite_test_client()

    invalid = client.post("/api/v1/conversations/messages", headers={"X-Johnny-User-Id": "user-1"}, json={"content": "   "})
    valid = client.post("/api/v1/conversations/messages", headers={"X-Johnny-User-Id": "user-1"}, json={"content": "How am I doing?"})
    recommendations = client.get("/api/v1/recommendations", headers={"X-Johnny-User-Id": "user-1"})

    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == "validation_error"
    assert valid.status_code == 200
    assert valid.json()["data"]["run_ref"]
    assert valid.json()["data"]["message"]["agent_status"] == "completed"
    assert valid.json()["data"]["message"]["agent_output"]
    assert recommendations.status_code == 200
    assert recommendations.json()["data"][0]["title"] == "Review today's training context"


def test_api_allows_local_vite_origin_for_browser_requests() -> None:
    from tests.unit.api_test_helpers import create_sqlite_test_client

    client = create_sqlite_test_client()

    response = client.options(
        "/api/v1/conversations/messages",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_integration_webhook_ingests_provider_payloads_and_counts_duplicates() -> None:
    from tests.unit.api_test_helpers import create_sqlite_test_client

    client = create_sqlite_test_client()
    connection = client.post(
        "/api/v1/integrations/connections",
        headers={"X-Johnny-User-Id": "user-1"},
        json={"provider": "garmin_connect", "provider_account_id": "garmin-account-1"},
    ).json()["data"]
    payload = {
        "activities": [
            {
                "activityId": "garmin-1",
                "activityType": {"typeKey": "running"},
                "startTimeGMT": "2027-01-02 07:00:00",
                "distance": 5000,
                "duration": 1500,
            }
        ],
        "health": [{"calendarDate": "2027-01-02", "get_rhr_day": {"restingHeartRate": 48}}],
        "cursor": {"after": "garmin-1"},
    }

    first = client.post(
        f"/api/v1/integrations/webhooks/garmin_connect/{connection['id']}",
        headers={"X-Johnny-User-Id": "user-1"},
        json=payload,
    )
    second = client.post(
        f"/api/v1/integrations/webhooks/garmin_connect/{connection['id']}",
        headers={"X-Johnny-User-Id": "user-1"},
        json=payload,
    )
    missing = client.post(
        "/api/v1/integrations/webhooks/garmin_connect/missing",
        headers={"X-Johnny-User-Id": "user-1"},
        json=payload,
    )

    assert first.status_code == 200
    assert first.json()["data"]["resources"]["activities"]["stored"] == 1
    assert second.json()["data"]["resources"]["activities"]["duplicates"] == 1
    assert missing.status_code == 404


def test_sync_provider_connection_replaces_reactivates_and_rejects_cross_user_accounts() -> None:
    from tests.unit.api_test_helpers import create_sqlite_test_client

    client = create_sqlite_test_client()
    garmin = client.post(
        "/api/v1/integrations/connections",
        headers={"X-Johnny-User-Id": "user-1"},
        json={"provider": "garmin_connect", "provider_account_id": "garmin-account-1"},
    )
    coros = client.post(
        "/api/v1/integrations/connections",
        headers={"X-Johnny-User-Id": "user-1"},
        json={"provider": "coros", "provider_account_id": "coros-account-1"},
    )
    reactivated = client.post(
        "/api/v1/integrations/connections",
        headers={"X-Johnny-User-Id": "user-1"},
        json={"provider": "garmin_connect", "provider_account_id": "garmin-account-1"},
    )
    cross_user_conflict = client.post(
        "/api/v1/integrations/connections",
        headers={"X-Johnny-User-Id": "user-2"},
        json={"provider": "garmin_connect", "provider_account_id": "garmin-account-1"},
    )
    missing_account = client.post(
        "/api/v1/integrations/connections",
        headers={"X-Johnny-User-Id": "user-1"},
        json={"provider": "garmin_connect"},
    )

    assert garmin.status_code == 200
    assert garmin.json()["data"]["status"] == "active"
    assert coros.status_code == 200
    assert coros.json()["data"]["status"] == "active"
    assert coros.json()["data"]["id"] != garmin.json()["data"]["id"]
    assert reactivated.status_code == 200
    assert reactivated.json()["data"]["id"] == garmin.json()["data"]["id"]
    assert reactivated.json()["data"]["status"] == "active"
    assert reactivated.json()["data"]["provider_account_id"] == "garmin-account-1"
    assert cross_user_conflict.status_code == 409
    assert cross_user_conflict.json()["error"]["code"] == "conflict"
    assert missing_account.status_code == 422
    assert missing_account.json()["error"]["code"] == "validation_error"


def test_integration_connection_response_does_not_expose_encrypted_credential_fields() -> None:
    from tests.unit.api_test_helpers import create_sqlite_test_client

    client = create_sqlite_test_client()

    response = client.post(
        "/api/v1/integrations/connections",
        headers={"X-Johnny-User-Id": "user-1"},
        json={
            "provider": "garmin_connect",
            "provider_account_id": "garmin-account-redacted",
            "encrypted_payload": "fernet:gAAAAABtoken",
            "lifecycle_metadata": {"email": "runner@example.com", "region": "global"},
        },
    )

    assert response.status_code == 200
    assert "encrypted_payload" not in response.json()["data"]
    assert "lifecycle_metadata" not in response.json()["data"]
    assert "runner@example.com" not in response.text
    assert "gAAAAABtoken" not in response.text


def test_garmin_credential_configuration_errors_are_redacted_http_errors() -> None:
    from tests.unit.api_test_helpers import create_sqlite_test_client
    from src.infrastructure.security.integration_credentials import CredentialEncryptionConfigurationError

    client = create_sqlite_test_client()

    @client.app.get("/api/v1/test-garmin-credential-configuration")
    def broken_garmin_configuration() -> None:
        raise CredentialEncryptionConfigurationError("GARMIN_CREDENTIAL_MASTER_KEY is invalid")

    response = client.get("/api/v1/test-garmin-credential-configuration")

    assert response.status_code == 503
    assert response.json()["error"] == {
        "code": "configuration_error",
        "message": "Garmin credential encryption is not configured",
        "details": [],
    }


def test_garmin_connect_endpoint_uses_discovered_identity_and_redacts_credentials() -> None:
    from tests.unit.api_test_helpers import create_sqlite_test_client
    from src.api.routes.integrations import get_garmin_credential_cipher, get_garmin_login_adapter, get_garmin_resource_adapter
    from src.application.integrations import GarminAccountProfile

    client = create_sqlite_test_client()
    garmin = _ApiFakeGarminLoginAdapter(
        GarminAccountProfile(
            provider_account_id="garmin-account-api",
            display_name="Garmin Runner",
            session_payload='{"oauth2_token":"secret-token"}',
        )
    )
    client.app.dependency_overrides[get_garmin_login_adapter] = lambda: garmin
    client.app.dependency_overrides[get_garmin_credential_cipher] = lambda: _ApiFakeCipher()
    client.app.dependency_overrides[get_garmin_resource_adapter] = lambda: _ApiFakeGarminResourceAdapter()
    client.put(
        "/api/v1/athlete/profile",
        headers={"X-Johnny-User-Id": "user-1"},
        json={
            "timezone": "Asia/Taipei",
            "experience_level": "intermediate",
            "current_weekly_mileage": 42,
            "preferred_training_days": ["tuesday", "thursday", "sunday"],
            "preferred_long_run_day": "sunday",
            "max_runs_per_week": 4,
        },
    )

    response = client.post(
        "/api/v1/integrations/garmin/connect",
        headers={"X-Johnny-User-Id": "user-1"},
        json={
            "email": "runner@example.com",
            "password": "garmin-password",
            "region": "china",
        },
    )
    reconnected = client.post(
        "/api/v1/integrations/garmin/connect",
        headers={"X-Johnny-User-Id": "user-1"},
        json={
            "email": "runner@example.com",
            "password": "new-garmin-password",
            "region": "global",
        },
    )
    cross_user = client.post(
        "/api/v1/integrations/garmin/connect",
        headers={"X-Johnny-User-Id": "user-2"},
        json={
            "email": "other@example.com",
            "password": "other-garmin-password",
            "region": "global",
        },
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["provider"] == "garmin_connect"
    assert data["provider_account_id"] == "garmin-account-api"
    assert data["provider_display_name"] == "Garmin Runner"
    assert data["credential_secret_ref"] is None
    assert data["credential_format"] == "garminconnect-session-json"
    assert data["sync_summary"]["resources"]["activities"]["stored"] == 1
    assert data["sync_summary"]["resources"]["sleep"]["stored"] == 1
    assert data["sync_summary"]["resources"]["hrv"]["stored"] == 1
    assert data["sync_summary"]["resources"]["resting_heart_rate"]["stored"] == 1
    assert data["sync_summary"]["resources"]["stress"]["stored"] == 1
    assert data["sync_summary"]["resources"]["body_battery"]["stored"] == 1
    assert "steps" not in data["sync_summary"]["resources"]
    assert "spo2" not in data["sync_summary"]["resources"]
    assert "garmin-password" not in response.text
    assert "runner@example.com" not in response.text
    assert "secret-token" not in response.text
    assert reconnected.status_code == 200
    assert reconnected.json()["data"]["id"] == data["id"]
    assert cross_user.status_code == 409
    assert garmin.calls[0] == {"email": "runner@example.com", "password": "garmin-password", "region": "china"}
    activities = client.get(
        "/api/v1/activities?started_on_or_after=2027-01-01&started_on_or_before=2027-01-31",
        headers={"X-Johnny-User-Id": "user-1"},
    )
    health = client.get(
        "/api/v1/health-metrics/daily?measured_on_or_after=2027-01-01&measured_on_or_before=2027-01-31",
        headers={"X-Johnny-User-Id": "user-1"},
    )
    assert activities.json()["data"][0]["source"] == "garmin_connect"
    assert health.json()["data"][0]["values"]["sleep_duration_minutes"] == 480
    assert health.json()["data"][0]["values"]["hrv_ms"] == 55
    assert health.json()["data"][0]["values"]["resting_heart_rate"] == 48
    assert health.json()["data"][0]["values"]["stress_score"] == 31
    assert health.json()["data"][0]["values"]["body_battery_score"] == 72


def test_garmin_connect_endpoint_rejects_user_entered_provider_account_id(monkeypatch) -> None:
    from cryptography.fernet import Fernet
    from tests.unit.api_test_helpers import create_sqlite_test_client

    monkeypatch.setenv("GARMIN_CREDENTIAL_MASTER_KEY", Fernet.generate_key().decode("ascii"))
    client = create_sqlite_test_client()

    response = client.post(
        "/api/v1/integrations/garmin/connect",
        headers={"X-Johnny-User-Id": "user-1"},
        json={
            "email": "runner@example.com",
            "password": "garmin-password",
            "region": "global",
            "provider_account_id": "user-supplied-id",
        },
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
    assert "user-supplied-id" not in response.text
    assert "garmin-password" not in response.text


def test_garmin_connect_validation_errors_do_not_echo_password(monkeypatch) -> None:
    from cryptography.fernet import Fernet
    from tests.unit.api_test_helpers import create_sqlite_test_client

    monkeypatch.setenv("GARMIN_CREDENTIAL_MASTER_KEY", Fernet.generate_key().decode("ascii"))
    client = create_sqlite_test_client()

    response = client.post(
        "/api/v1/integrations/garmin/connect",
        headers={"X-Johnny-User-Id": "user-1"},
        json={
            "email": "runner@example.com",
            "password": "",
            "region": "global",
        },
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
    assert "runner@example.com" not in response.text
    assert "password" not in response.text
    assert "garmin-password" not in response.text


def test_garmin_connect_endpoint_reports_unconfigured_adapter_without_echoing_credentials(monkeypatch) -> None:
    from cryptography.fernet import Fernet
    from tests.unit.api_test_helpers import create_sqlite_test_client

    monkeypatch.setenv("GARMIN_CREDENTIAL_MASTER_KEY", Fernet.generate_key().decode("ascii"))
    client = create_sqlite_test_client()

    response = client.post(
        "/api/v1/integrations/garmin/connect",
        headers={"X-Johnny-User-Id": "user-1"},
        json={
            "email": "runner@example.com",
            "password": "garmin-password",
            "region": "global",
        },
    )

    assert response.status_code == 503
    assert response.json()["error"] == {
        "code": "configuration_error",
        "message": "Garmin integration is not configured",
        "details": [],
    }
    assert "runner@example.com" not in response.text
    assert "garmin-password" not in response.text


class _ApiFakeGarminLoginAdapter:
    def __init__(self, profile) -> None:
        self._profile = profile
        self.calls: list[dict[str, str]] = []

    def exchange_credentials(self, *, email: str, password: str, region: str):
        self.calls.append({"email": email, "password": password, "region": region})
        return self._profile


class _ApiFakeCipher:
    key_id = "local-fernet"

    def encrypt(self, plaintext: str) -> str:
        assert plaintext == '{"oauth2_token":"secret-token"}'
        return "fernet:encrypted-session"

    def decrypt(self, encrypted_payload: str) -> str:
        raise AssertionError("connect should not decrypt credentials")


class _ApiFakeGarminResourceAdapter:
    def fetch_resource(self, *, connection, resource_type, start_date, end_date, timezone_name, cursor):
        from src.application.integrations import GarminResourceFetchResult

        assert timezone_name == "Asia/Taipei"
        assert start_date <= end_date
        payloads = {
            "activities": [
                {
                    "activityId": "garmin-activity-1",
                    "activityType": {"typeKey": "running"},
                    "startTimeGMT": "2027-01-10 07:00:00",
                    "distance": 5000,
                    "duration": 1500,
                }
            ],
            "sleep": [
                {
                    "calendarDate": "2027-01-10",
                    "get_sleep_data": {
                        "dailySleepDTO": {"sleepTimeSeconds": 28800},
                        "sleepScores": {"overall": {"value": 82}},
                    },
                }
            ],
            "hrv": [
                {
                    "calendarDate": "2027-01-10",
                    "get_hrv_data": {"hrvSummary": {"lastNightAvg": 55, "weeklyAvg": 52}},
                }
            ],
            "resting_heart_rate": [{"calendarDate": "2027-01-10", "get_rhr_day": {"restingHeartRate": 48}}],
            "stress": [{"calendarDate": "2027-01-10", "get_stress_data": {"avgStressLevel": 31}}],
            "body_battery": [{"calendarDate": "2027-01-10", "get_body_battery": {"bodyBatteryValuesArray": [[0, 72]]}}],
        }
        return GarminResourceFetchResult(items=payloads.get(resource_type, []), cursor={"date": end_date.isoformat()})
