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


def test_today_and_recommendations_routes_accept_legacy_action_type_payload() -> None:
    from tests.unit.api_test_helpers import create_sqlite_test_client

    client = create_sqlite_test_client()
    headers = {"X-Johnny-User-Id": "legacy-action-user"}
    created = client.post(
        "/api/v1/recommendations",
        headers=headers,
        json={
            "recommendation_type": "informational",
            "priority": "medium",
            "title": "Legacy action",
            "rationale": "Stored clients may still send action_type.",
            "evidence": [{"source": "legacy", "metric": "readiness_label", "value": "ready"}],
            "proposed_action": {"action_type": "no_plan_change", "reason": "Informational only"},
        },
    )
    listed = client.get("/api/v1/recommendations", headers=headers)
    today = client.get("/api/v1/today?anchor_date=2027-01-02", headers=headers)

    assert created.status_code == 200
    assert created.json()["data"]["proposed_action"]["type"] == "no_plan_change"
    assert listed.status_code == 200
    assert listed.json()["data"][0]["proposed_action"]["type"] == "no_plan_change"
    assert today.status_code == 200
    assert today.json()["data"]["current_recommendation"]["title"] == "Legacy action"


def test_today_and_recommendations_routes_read_historical_training_plan_creation_action() -> None:
    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine, event
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from src.api.dependencies import get_session
    from src.infrastructure.database.models import Base, RecommendationModel, UserModel
    from src.main import create_app

    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(dbapi_connection, connection_record) -> None:  # noqa: ANN001
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)

    def override_session():
        session = session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    app = create_app()
    app.dependency_overrides[get_session] = override_session
    client = TestClient(app)
    with session_factory() as session:
        user = UserModel(
            id="historical-plan-action-user",
            email="historical-plan-action@example.com",
            display_name="Historical Plan Action",
        )
        session.add(user)
        session.flush()
        session.add(
            RecommendationModel(
                user_id=user.id,
                title="Review generated plan",
                rationale="Legacy draft-plan recommendation.",
                evidence={
                    "items": [{"source": "legacy_agent", "metric": "workflow", "value": "training_plan_generation"}],
                    "recommendation": {"type": "training_plan_creation", "priority": "medium"},
                    "proposed_action": {
                        "type": "create_training_plan",
                        "draft_training_plan_id": "draft-plan-1",
                        "reason": "Approve generated plan.",
                    },
                },
            )
        )
        session.commit()

    headers = {"X-Johnny-User-Id": "historical-plan-action-user"}
    listed = client.get("/api/v1/recommendations", headers=headers)
    today = client.get("/api/v1/today?anchor_date=2027-01-02", headers=headers)

    assert listed.status_code == 200
    assert listed.json()["data"][0]["recommendation_type"] == "informational"
    assert listed.json()["data"][0]["proposed_action"]["type"] == "no_plan_change"
    assert today.status_code == 200
    assert today.json()["data"]["current_recommendation"]["title"] == "Review generated plan"


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


def test_async_agent_run_routes_queue_daily_and_training_plan_generation_and_poll_user_runs() -> None:
    from tests.unit.api_test_helpers import create_sqlite_test_client

    client = create_sqlite_test_client()
    headers = {"X-Johnny-User-Id": "user-1"}

    daily = client.post(
        "/api/v1/agent-runs/daily-recommendation",
        headers=headers,
        json={"anchor_date": "2027-01-28"},
    )
    duplicate = client.post(
        "/api/v1/agent-runs/daily-recommendation",
        headers=headers,
        json={"anchor_date": "2027-01-28"},
    )
    forced = client.post(
        "/api/v1/agent-runs/daily-recommendation",
        headers=headers,
        json={"anchor_date": "2027-01-28", "force": True},
    )
    training = client.post(
        "/api/v1/agent-runs/training-plan-generation",
        headers=headers,
        json={"plan_type": "base", "starts_on": "2027-02-01", "plan_horizon_weeks": 4},
    )
    competing_training = client.post(
        "/api/v1/agent-runs/training-plan-generation",
        headers=headers,
        json={"plan_type": "race", "starts_on": "2027-03-01", "plan_horizon_weeks": 8},
    )
    polled = client.get(daily.json()["data"]["poll_url"], headers=headers)
    steps = client.get(f"/api/v1/agent-runs/{daily.json()['data']['run_id']}/steps", headers=headers)
    listed = client.get("/api/v1/agent-runs?status=queued", headers=headers)
    hidden = client.get(daily.json()["data"]["poll_url"], headers={"X-Johnny-User-Id": "user-2"})

    assert daily.status_code == 200
    assert daily.json()["data"]["status"] == "queued"
    assert daily.json()["data"]["workflow_name"] == "daily_recommendation"
    assert daily.json()["data"]["poll_url"] == f"/api/v1/agent-runs/{daily.json()['data']['run_id']}"
    assert duplicate.json()["data"]["run_id"] == daily.json()["data"]["run_id"]
    assert forced.json()["data"]["run_id"] != daily.json()["data"]["run_id"]
    assert training.status_code == 200
    assert training.json()["data"]["workflow_name"] == "training_plan_generation"
    assert competing_training.json()["data"]["run_id"] == training.json()["data"]["run_id"]
    assert polled.json()["data"]["id"] == daily.json()["data"]["run_id"]
    assert polled.json()["data"]["started_at"] is None
    assert steps.json()["data"] == []
    assert {run["workflow_name"] for run in listed.json()["data"]} == {
        "daily_recommendation",
        "training_plan_generation",
    }
    assert hidden.status_code == 404


def test_plan_recommendation_api_blocks_cross_user_accept_without_plan_activation() -> None:
    from tests.unit.api_test_helpers import create_sqlite_test_client

    client = create_sqlite_test_client()
    owner_headers = {"X-Johnny-User-Id": "user-1"}
    other_headers = {"X-Johnny-User-Id": "user-2"}
    plan = client.post(
        "/api/v1/training-plans",
        headers=owner_headers,
        json={
            "name": "Generated Active Plan",
            "starts_on": "2027-01-01",
            "ends_on": "2027-01-28",
            "status": "active",
            "workouts": [
                {
                    "scheduled_for": "2027-01-03",
                    "workout_type": "easy_run",
                    "purpose": "Aerobic base",
                    "planned_duration_minutes": 40,
                }
            ],
        },
    ).json()["data"]
    recommendation = client.post(
        "/api/v1/recommendations",
        headers=owner_headers,
        json={
            "recommendation_type": "informational",
            "priority": "medium",
            "title": "Training plan created",
            "rationale": "An active generated plan is ready.",
            "evidence": [{"source": "agent", "metric": "plan_weeks", "value": 4}],
            "proposed_action": {
                "type": "no_plan_change",
                "reason": "The plan has already been created.",
            },
            "training_plan_id": plan["id"],
        },
    ).json()["data"]

    other_accept = client.post(f"/api/v1/recommendations/{recommendation['id']}/accept", headers=other_headers)
    other_plan = client.get(f"/api/v1/training-plans/{plan['id']}", headers=other_headers)
    owner_accept = client.post(f"/api/v1/recommendations/{recommendation['id']}/accept", headers=owner_headers)
    owner_plan = client.get(f"/api/v1/training-plans/{plan['id']}", headers=owner_headers)

    assert other_accept.status_code == 404
    assert other_plan.status_code == 404
    assert owner_accept.json()["data"]["decision"] == "accepted"
    assert owner_plan.json()["data"]["status"] == "active"


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
            "current_weekly_mileage_km": 42,
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
    assert data["credential_status"] == "active"
    assert data["sync_status"] == "idle"
    assert data["last_sync_started_at"] is not None
    assert data["last_sync_completed_at"] is not None
    assert data["last_sync_error"] is None
    assert data["has_partial_failures"] is False
    assert data["sync_warning"] is None
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


def test_garmin_connect_endpoint_returns_reauth_state_when_initial_sync_is_credential_blocked() -> None:
    from tests.unit.api_test_helpers import create_sqlite_test_client
    from src.api.routes.integrations import get_garmin_credential_cipher, get_garmin_login_adapter, get_garmin_resource_adapter
    from src.application.integrations import GarminAccountProfile

    client = create_sqlite_test_client()
    client.app.dependency_overrides[get_garmin_login_adapter] = lambda: _ApiFakeGarminLoginAdapter(
        GarminAccountProfile(
            provider_account_id="garmin-account-reauth",
            display_name="Garmin Runner",
            session_payload='{"oauth2_token":"secret-token"}',
        )
    )
    client.app.dependency_overrides[get_garmin_credential_cipher] = lambda: _ApiFakeCipher()
    client.app.dependency_overrides[get_garmin_resource_adapter] = lambda: _ApiFakeGarminCredentialBlockedResourceAdapter()

    response = client.post(
        "/api/v1/integrations/garmin/connect",
        headers={"X-Johnny-User-Id": "user-1"},
        json={
            "email": "runner@example.com",
            "password": "garmin-password",
            "region": "global",
        },
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["credential_status"] == "requires_reauth"
    assert data["sync_status"] == "failed"
    assert data["last_sync_started_at"] is not None
    assert data["last_sync_completed_at"] is not None
    assert data["last_sync_error"] == "Garmin connection requires reauth"
    assert data["has_partial_failures"] is False
    assert data["sync_warning"] == "Garmin connection requires reauth"
    assert data["sync_summary"]["resources"]["activities"]["errors"] == ["Garmin connection requires reauth"]
    assert "session-secret" not in response.text
    assert "secret-token" not in response.text
    assert "garmin-password" not in response.text


def test_training_plan_regeneration_options_returns_quota_strategy_and_run_slots() -> None:
    from datetime import date, timedelta

    from tests.unit.api_test_helpers import create_sqlite_test_client

    client = create_sqlite_test_client()
    headers = {"X-Johnny-User-Id": "regeneration-options-user"}
    race_date = date.today() + timedelta(days=80)
    race = client.post(
        "/api/v1/races",
        headers=headers,
        json={
            "name": "Priority Half",
            "race_date": race_date.isoformat(),
            "distance_meters": 21097,
            "priority": "primary",
        },
    ).json()["data"]

    response = client.get("/api/v1/training-plans/regeneration-options", headers=headers)

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["quota"] == {
        "quota_day": date.today().isoformat(),
        "limit": 1,
        "used": 0,
        "remaining": 1,
        "available": True,
        "next_available_at": None,
    }
    assert data["default_strategy"]["race_id"] == race["id"]
    assert data["default_strategy"]["plan_type"] == "race"
    assert data["default_strategy"]["plan_horizon_weeks"] == 12
    assert data["in_flight_run"] is None
    assert data["run"] is None


def test_regeneration_without_race_id_uses_options_current_plan_race() -> None:
    from datetime import date, timedelta

    from sqlalchemy import select

    from src.infrastructure.database.models import AgentRunModel, TrainingPlanModel

    client, session_factory = _create_regeneration_api_client()
    headers = {"X-Johnny-User-Id": "current-plan-race-user"}
    race_date = (date.today() + timedelta(days=80)).isoformat()
    primary = client.post(
        "/api/v1/races", headers=headers,
        json={"name": "Primary", "race_date": race_date, "distance_meters": 21097, "priority": "primary"},
    ).json()["data"]
    current_race = client.post(
        "/api/v1/races", headers=headers,
        json={"name": "Current", "race_date": race_date, "distance_meters": 10000, "priority": "secondary"},
    ).json()["data"]
    with session_factory() as session:
        session.add(TrainingPlanModel(
            user_id="current-plan-race-user", race_id=current_race["id"], name="Active Projection",
            starts_on=date.today(), ends_on=date.today() + timedelta(days=28), status="active",
            metadata_json={},
        ))
        session.commit()

    options = client.get("/api/v1/training-plans/regeneration-options", headers=headers)
    started = client.post(
        "/api/v1/training-plans/regenerations", headers=headers,
        json={"client_request_id": "default-current-race", "plan_type": "race"},
    )

    assert primary["id"] != current_race["id"]
    assert options.status_code == 200
    assert started.status_code == 200
    assert options.json()["data"]["default_strategy"]["race_id"] == current_race["id"]
    assert started.json()["data"]["default_strategy"] == options.json()["data"]["default_strategy"]
    with session_factory() as session:
        run = session.scalar(select(AgentRunModel).where(
            AgentRunModel.id == started.json()["data"]["run"]["run_id"]
        ))
        assert run.metadata_json["race_id"] == current_race["id"]


def test_regeneration_queue_pins_provider_and_reuses_run_after_environment_change(monkeypatch) -> None:
    from sqlalchemy import select

    from src.infrastructure.database.models import AgentRunModel

    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("LLM_MODEL", "test-model")
    client, session_factory = _create_regeneration_api_client()
    headers = {"X-Johnny-User-Id": "provider-regeneration-user"}
    payload = {"client_request_id": "provider-request", "plan_type": "maintenance"}
    first = client.post("/api/v1/training-plans/regenerations", headers=headers, json=payload)
    monkeypatch.delenv("LLM_API_KEY")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    second = client.post("/api/v1/training-plans/regenerations", headers=headers, json=payload)

    assert first.status_code == second.status_code == 200
    assert first.json()["data"]["run"]["run_id"] == second.json()["data"]["run"]["run_id"]
    with session_factory() as session:
        run = session.scalar(select(AgentRunModel).where(
            AgentRunModel.id == first.json()["data"]["run"]["run_id"]
        ))
        assert (run.provider, run.model) == ("openai", "test-model")


def test_raw_training_plan_queue_selects_openai_without_changing_daily_provider(monkeypatch) -> None:
    from tests.unit.api_test_helpers import create_sqlite_test_client

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.setenv("LLM_MODEL", "test-model")
    client = create_sqlite_test_client()
    headers = {"X-Johnny-User-Id": "provider-raw-user"}
    training = client.post(
        "/api/v1/agent-runs/training-plan-generation", headers=headers,
        json={"plan_type": "base", "starts_on": "2027-02-01"},
    )
    daily = client.post(
        "/api/v1/agent-runs/daily-recommendation", headers=headers,
        json={"anchor_date": "2027-02-01"},
    )

    assert training.status_code == daily.status_code == 200
    training_run = client.get(training.json()["data"]["poll_url"], headers=headers).json()["data"]
    daily_run = client.get(daily.json()["data"]["poll_url"], headers=headers).json()["data"]
    assert (training_run["provider"], training_run["model"]) == ("openai", "test-model")
    assert (daily_run["provider"], daily_run["model"]) == ("local", "deterministic-local-companion")


def test_training_plan_regeneration_options_returns_exhausted_quota_payload() -> None:
    from datetime import date, datetime, timezone

    from src.domain.agent_runtime import AgentRun
    from src.infrastructure.database.agent_run_repository import SqlAlchemyAgentRunRepository

    client, session_factory = _create_regeneration_api_client()
    headers = {"X-Johnny-User-Id": "quota-exhausted-user"}
    assert client.get("/api/v1/training-plans/regeneration-options", headers=headers).status_code == 200
    with session_factory() as session:
        SqlAlchemyAgentRunRepository(session).create_run(
            AgentRun(
                user_id="quota-exhausted-user",
                trigger_type="manual",
                workflow_name="training_plan_generation",
                prompt_version="v1",
                status="completed",
                finished_at=datetime.now(timezone.utc),
                metadata={
                    "manual_regeneration": True,
                    "quota_day": date.today().isoformat(),
                    "created_training_plan_id": "created-plan",
                },
            )
        )
        session.commit()

    response = client.get("/api/v1/training-plans/regeneration-options", headers=headers)
    blocked = client.post(
        "/api/v1/training-plans/regenerations",
        headers=headers,
        json={"client_request_id": "blocked-by-quota", "plan_type": "maintenance"},
    )

    assert response.status_code == 200
    assert response.json()["data"]["quota"]["available"] is False
    assert response.json()["data"]["quota"]["next_available_at"] is not None
    assert blocked.status_code == 200
    assert blocked.json()["data"]["run"] is None


def test_development_quota_override_is_visible_to_ui_and_production_ignores_it(monkeypatch) -> None:
    from datetime import datetime, timezone

    from src.domain.agent_runtime import AgentRun
    from src.infrastructure.database.agent_run_repository import SqlAlchemyAgentRunRepository

    monkeypatch.setenv("JOHNNY_DEV_REGENERATION_DAILY_LIMIT", "10")
    monkeypatch.setenv("JOHNNY_AUTH_ALLOW_HEADER_USER", "true")
    monkeypatch.setenv("ENV", "development")
    client, session_factory = _create_regeneration_api_client()
    headers = {"X-Johnny-User-Id": "dev-quota-user"}
    assert client.get("/api/v1/training-plans/regeneration-options", headers=headers).status_code == 200
    with session_factory() as session:
        SqlAlchemyAgentRunRepository(session).create_run(AgentRun(
            user_id="dev-quota-user", trigger_type="manual", workflow_name="training_plan_generation",
            prompt_version="v1", status="completed", finished_at=datetime.now(timezone.utc),
            metadata={"manual_regeneration": True, "created_training_plan_id": "previous-plan"},
        ))
        session.commit()

    development = client.get("/api/v1/training-plans/regeneration-options", headers=headers)
    assert development.status_code == 200
    assert development.json()["data"]["quota"]["limit"] == 10
    assert development.json()["data"]["quota"]["used"] == 1
    queued = client.post("/api/v1/training-plans/regenerations", headers=headers, json={
        "client_request_id": "dev-second-request", "plan_type": "maintenance",
    })
    assert queued.status_code == 200
    assert queued.json()["data"]["run"] is not None

    monkeypatch.setenv("ENV", "production")
    production = client.get("/api/v1/training-plans/regeneration-options", headers=headers)
    assert production.status_code == 200
    assert production.json()["data"]["quota"]["limit"] == 1


def test_athlete_profile_threshold_pace_round_trips_and_validates() -> None:
    from tests.unit.api_test_helpers import create_sqlite_test_client

    client = create_sqlite_test_client()
    headers = {"X-Johnny-User-Id": "pace-profile-user"}
    payload = {
        "timezone": "Asia/Taipei", "current_weekly_mileage_km": 40,
        "preferred_training_days": ["tuesday", "sunday"],
        "preferred_long_run_day": "sunday", "max_runs_per_week": 5,
        "training_preferences": {"surface": "trail"},
        "threshold_pace_seconds_per_km": 300,
    }

    saved = client.put("/api/v1/athlete/profile", headers=headers, json=payload)
    assert saved.status_code == 200
    assert saved.json()["data"]["threshold_pace_seconds_per_km"] == 300
    assert saved.json()["data"]["training_preferences"] == {"surface": "trail", "threshold_pace_seconds_per_km": 300}

    loaded = client.get("/api/v1/athlete/profile", headers=headers)
    assert loaded.json()["data"]["threshold_pace_seconds_per_km"] == 300
    invalid = client.put("/api/v1/athlete/profile", headers=headers, json={**payload, "threshold_pace_seconds_per_km": -1})
    assert invalid.status_code == 422

    cleared = client.put("/api/v1/athlete/profile", headers=headers, json={**payload, "threshold_pace_seconds_per_km": None})
    assert cleared.status_code == 200
    assert cleared.json()["data"]["threshold_pace_seconds_per_km"] is None
    assert cleared.json()["data"]["training_preferences"] == {"surface": "trail"}


def test_training_plan_regeneration_options_selects_maintenance_without_future_races() -> None:
    from datetime import date, timedelta

    from tests.unit.api_test_helpers import create_sqlite_test_client

    client = create_sqlite_test_client()

    response = client.get(
        "/api/v1/training-plans/regeneration-options",
        headers={"X-Johnny-User-Id": "maintenance-options-user"},
    )

    assert response.status_code == 200
    assert response.json()["data"]["default_strategy"] == {
        "race_id": None,
        "plan_type": "maintenance",
        "reason": "no_future_race",
        "starts_on": (date.today() + timedelta(days=1)).isoformat(),
        "plan_horizon_weeks": 4,
    }


def test_training_plan_regeneration_start_reuses_in_flight_run() -> None:
    from tests.unit.api_test_helpers import create_sqlite_test_client

    client = create_sqlite_test_client()
    headers = {"X-Johnny-User-Id": "in-flight-user"}

    first = client.post(
        "/api/v1/training-plans/regenerations",
        headers=headers,
        json={"client_request_id": "first-confirmation", "plan_type": "maintenance"},
    )
    second = client.post(
        "/api/v1/training-plans/regenerations",
        headers=headers,
        json={"client_request_id": "different-confirmation", "plan_type": "maintenance"},
    )
    options = client.get("/api/v1/training-plans/regeneration-options", headers=headers)

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["data"]["run"] == first.json()["data"]["run"]
    assert second.json()["data"]["in_flight_run"] == first.json()["data"]["run"]
    assert options.json()["data"]["in_flight_run"] == first.json()["data"]["run"]


def test_training_plan_regeneration_route_maps_request_to_application_value(monkeypatch) -> None:
    from src.api.dependencies import CurrentUser
    from src.api.routes import training_plan_regeneration as route
    from src.api.schemas.training_plan_regeneration import TrainingPlanRegenerationRequest
    from src.application.training_plan_regeneration import RegenerationRequest

    session = object()

    class CommandHandler:
        def handle(self, *, user_id, request, today):
            assert user_id == "lock-user"
            assert isinstance(request, RegenerationRequest)
            assert request == RegenerationRequest("lock-check", "maintenance", None)
            return object()

    monkeypatch.setattr(route, "ensure_current_user", lambda session, current_user: object())
    monkeypatch.setattr(route, "_response", lambda result: {})

    response = route.start_regeneration(
        TrainingPlanRegenerationRequest(client_request_id="lock-check", plan_type="maintenance"),
        CurrentUser(id="lock-user"),
        session,
        CommandHandler(),
    )

    assert response.data == {}


def test_training_plan_regeneration_post_validates_and_returns_queued_product_run() -> None:
    from datetime import date, timedelta

    from sqlalchemy import select

    from src.infrastructure.database.models import AgentRunModel, AgentTaskModel

    client, session_factory = _create_regeneration_api_client()
    headers = {"X-Johnny-User-Id": "regeneration-post-user"}
    race_date = date.today() + timedelta(days=30)
    race_id = client.post(
        "/api/v1/races",
        headers=headers,
        json={"name": "Ten K", "race_date": race_date.isoformat(), "distance_meters": 10000},
    ).json()["data"]["id"]

    empty_id = client.post(
        "/api/v1/training-plans/regenerations",
        headers=headers,
        json={"client_request_id": "", "race_id": race_id},
    )
    invalid_type = client.post(
        "/api/v1/training-plans/regenerations",
        headers=headers,
        json={"client_request_id": "bad-type", "plan_type": "base"},
    )
    queued = client.post(
        "/api/v1/training-plans/regenerations",
        headers=headers,
        json={"client_request_id": "race-confirmation", "race_id": race_id},
    )

    assert empty_id.status_code == 422
    assert invalid_type.status_code == 422
    assert queued.status_code == 200
    data = queued.json()["data"]
    assert data["run"]["status"] == "queued"
    assert data["run"]["workflow_name"] == "training_plan_generation"
    assert data["run"]["poll_url"] == f"/api/v1/agent-runs/{data['run']['run_id']}"
    with session_factory() as session:
        run = session.scalar(select(AgentRunModel).where(AgentRunModel.id == data["run"]["run_id"]))
        task = session.scalar(select(AgentTaskModel).where(AgentTaskModel.payload["run_id"].as_string() == run.id))
        assert run.metadata_json == {
            "async": True,
            "race_id": race_id,
            "plan_type": "race",
            "starts_on": (date.today() + timedelta(days=1)).isoformat(),
            "plan_horizon_weeks": 5,
            "client_request_id": "race-confirmation",
            "manual_regeneration": True,
            "quota_day": date.today().isoformat(),
        }
        assert task.payload["input"] == {
            "race_id": race_id,
            "plan_type": "race",
            "starts_on": (date.today() + timedelta(days=1)).isoformat(),
            "plan_horizon_weeks": 5,
            "client_request_id": "race-confirmation",
            "manual_regeneration": True,
            "quota_day": date.today().isoformat(),
        }


def _create_regeneration_api_client():
    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine, event
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from src.api.dependencies import get_session
    from src.infrastructure.database.models import Base
    from src.main import create_app

    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(dbapi_connection, connection_record) -> None:  # noqa: ANN001
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)

    def override_session():
        session = session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    app = create_app()
    app.dependency_overrides[get_session] = override_session
    return TestClient(app), session_factory


def test_garmin_connect_endpoint_reports_partial_failure_after_zero_item_successes() -> None:
    from tests.unit.api_test_helpers import create_sqlite_test_client
    from src.api.routes.integrations import get_garmin_credential_cipher, get_garmin_login_adapter, get_garmin_resource_adapter
    from src.application.integrations import GarminAccountProfile

    client = create_sqlite_test_client()
    client.app.dependency_overrides[get_garmin_login_adapter] = lambda: _ApiFakeGarminLoginAdapter(
        GarminAccountProfile(
            provider_account_id="garmin-account-partial",
            display_name="Garmin Runner",
            session_payload='{"oauth2_token":"secret-token"}',
        )
    )
    client.app.dependency_overrides[get_garmin_credential_cipher] = lambda: _ApiFakeCipher()
    client.app.dependency_overrides[get_garmin_resource_adapter] = lambda: _ApiFakeGarminZeroItemPartialFailureResourceAdapter()

    response = client.post(
        "/api/v1/integrations/garmin/connect",
        headers={"X-Johnny-User-Id": "user-1"},
        json={
            "email": "runner@example.com",
            "password": "garmin-password",
            "region": "global",
        },
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["credential_status"] == "active"
    assert data["sync_status"] == "idle"
    assert data["has_partial_failures"] is True
    assert data["sync_warning"] == "Some Garmin resources failed to sync"
    assert data["sync_summary"]["resources"]["activities"]["fetched"] == 0
    assert data["sync_summary"]["resources"]["body_battery"]["errors"] == ["Garmin resource sync failed"]
    assert "abc-session" not in response.text


def test_integration_connections_endpoint_lists_current_users_active_connections() -> None:
    from tests.unit.api_test_helpers import create_sqlite_test_client

    client = create_sqlite_test_client()
    connected = _connect_api_garmin(
        client,
        provider_account_id="garmin-account-list",
        with_profile=True,
    )
    other_user = _connect_api_garmin(
        client,
        user_id="user-2",
        provider_account_id="garmin-account-other-list",
        email="other@example.com",
    )

    response = client.get(
        "/api/v1/integrations/connections",
        headers={"X-Johnny-User-Id": "user-1"},
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert [connection["id"] for connection in data] == [connected["id"]]
    assert data[0]["provider"] == "garmin_connect"
    assert data[0]["provider_display_name"] == "Garmin Runner"
    assert data[0]["last_sync_completed_at"] is not None
    assert data[0]["sync_summary"]["resources"]["activities"]["stored"] == 1
    assert data[0]["sync_summary"]["resources"]["body_battery"]["stored"] == 1
    assert other_user["id"] not in response.text
    assert "secret-token" not in response.text


def test_manual_garmin_sync_endpoint_returns_summary_and_uses_existing_import_path() -> None:
    from tests.unit.api_test_helpers import create_sqlite_test_client

    client = create_sqlite_test_client()
    adapter = _ApiFakeGarminResourceAdapter()
    connected = _connect_api_garmin(
        client,
        provider_account_id="garmin-account-manual",
        resource_adapter=adapter,
        with_profile=True,
    )

    response = client.post(
        f"/api/v1/integrations/connections/{connected['id']}/sync",
        headers={"X-Johnny-User-Id": "user-1"},
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["sync_status"] == "idle"
    assert data["sync_summary"]["resources"]["activities"]["duplicates"] == 1
    assert data["sync_summary"]["resources"]["sleep"]["stored"] == 1
    assert data["last_sync_started_at"] is not None
    assert data["last_sync_completed_at"] is not None
    assert "garmin-password" not in response.text
    assert "secret-token" not in response.text


def test_manual_garmin_sync_endpoint_reports_partial_failure_without_breaking_connection() -> None:
    from tests.unit.api_test_helpers import create_sqlite_test_client
    from src.api.routes.integrations import get_garmin_resource_adapter

    client = create_sqlite_test_client()
    connected = _connect_api_garmin(
        client,
        provider_account_id="garmin-account-manual-partial",
        with_profile=True,
    )
    client.app.dependency_overrides[get_garmin_resource_adapter] = lambda: _ApiFakeGarminZeroItemPartialFailureResourceAdapter()

    response = client.post(
        f"/api/v1/integrations/connections/{connected['id']}/sync",
        headers={"X-Johnny-User-Id": "user-1"},
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["credential_status"] == "active"
    assert data["sync_status"] == "idle"
    assert data["has_partial_failures"] is True
    assert data["sync_warning"] == "Some Garmin resources failed to sync"
    assert data["sync_summary"]["resources"]["body_battery"]["errors"] == ["Garmin resource sync failed"]


def test_manual_garmin_sync_endpoint_returns_reauth_state_without_fetching() -> None:
    from tests.unit.api_test_helpers import create_sqlite_test_client

    client = create_sqlite_test_client()
    blocked_adapter = _ApiFakeGarminCredentialBlockedResourceAdapter()
    connected = _connect_api_garmin(
        client,
        provider_account_id="garmin-account-manual-reauth",
        resource_adapter=blocked_adapter,
    )
    blocked_adapter.calls = 0

    response = client.post(
        f"/api/v1/integrations/connections/{connected['id']}/sync",
        headers={"X-Johnny-User-Id": "user-1"},
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["credential_status"] == "requires_reauth"
    assert data["sync_warning"] == "Garmin connection requires reauth"
    assert data["sync_summary"]["resources"]["sync"]["errors"] == ["Garmin connection requires reauth"]
    assert blocked_adapter.calls == 0


def test_manual_garmin_sync_endpoint_returns_existing_running_status_or_conflict(tmp_path) -> None:
    from concurrent.futures import ThreadPoolExecutor
    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from src.api.dependencies import get_session
    from src.api.routes.integrations import get_garmin_resource_adapter
    from src.infrastructure.database.integration_repository import SqlAlchemyIntegrationRepository
    from src.infrastructure.database.models import Base, IntegrationConnectionModel, UserModel
    from src.infrastructure.database.uow import SqlAlchemyUnitOfWork
    from src.main import create_app

    engine = create_engine(f"sqlite:///{tmp_path / 'manual-sync.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)

    def override_session():
        session = session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    app = create_app()
    app.dependency_overrides[get_session] = override_session
    blocking_adapter = _ApiBlockingGarminResourceAdapter()
    app.dependency_overrides[get_garmin_resource_adapter] = lambda: blocking_adapter
    client = TestClient(app)
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        user = UserModel(id="user-1", email="running@example.com", display_name="Running")
        uow.session.add(user)
        uow.session.flush()
        repository = SqlAlchemyIntegrationRepository(uow.session)
        running_connection = repository.create_connection(
            user_id=user.id,
            provider="garmin_connect",
            provider_account_id="garmin-running",
        )
        live_connection = repository.create_connection(
            user_id=user.id,
            provider="garmin_connect",
            provider_account_id="garmin-live-running",
        )
        stale_connection = repository.create_connection(
            user_id=user.id,
            provider="garmin_connect",
            provider_account_id="garmin-stale-running",
        )
        repository.start_sync_run(running_connection.id)
        stale_model = uow.session.get(IntegrationConnectionModel, stale_connection.id)
        assert stale_model is not None
        stale_model.sync_status = "running"
        uow.commit()

    stale = client.post(
        f"/api/v1/integrations/connections/{stale_connection.id}/sync",
        headers={"X-Johnny-User-Id": "user-1"},
    )
    with ThreadPoolExecutor(max_workers=2) as executor:
        first_future = executor.submit(
            client.post,
            f"/api/v1/integrations/connections/{live_connection.id}/sync",
            headers={"X-Johnny-User-Id": "user-1"},
        )
        assert blocking_adapter.entered.wait(timeout=5)
        running = client.post(
            f"/api/v1/integrations/connections/{live_connection.id}/sync",
            headers={"X-Johnny-User-Id": "user-1"},
        )
        blocking_adapter.release.set()
        first = first_future.result(timeout=5)

    assert first.status_code == 200
    assert running.status_code == 200
    assert running.json()["data"]["sync_status"] == "running"
    assert running.json()["data"]["last_sync_started_at"] is not None
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "conflict"


def test_garmin_disconnect_endpoint_deletes_secret_and_preserves_imported_data() -> None:
    from tests.unit.api_test_helpers import create_sqlite_test_client

    client = create_sqlite_test_client()
    connected = _connect_api_garmin(
        client,
        provider_account_id="garmin-account-disconnect-api",
        with_profile=True,
    )

    response = client.delete(
        f"/api/v1/integrations/connections/{connected['id']}",
        headers={"X-Johnny-User-Id": "user-1"},
    )
    sync_after_disconnect = client.post(
        f"/api/v1/integrations/connections/{connected['id']}/sync",
        headers={"X-Johnny-User-Id": "user-1"},
    )
    activities = client.get(
        "/api/v1/activities?started_on_or_after=2027-01-01&started_on_or_before=2027-01-31",
        headers={"X-Johnny-User-Id": "user-1"},
    )
    health = client.get(
        "/api/v1/health-metrics/daily?measured_on_or_after=2027-01-01&measured_on_or_before=2027-01-31",
        headers={"X-Johnny-User-Id": "user-1"},
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "disconnected"
    assert data["credential_status"] == "deleted"
    assert data["sync_status"] == "idle"
    assert data["provider_account_id"] == "garmin-account-disconnect-api"
    assert "encrypted_payload" not in data
    assert "secret-token" not in response.text
    assert sync_after_disconnect.status_code == 404
    assert activities.json()["data"][0]["source_activity_id"] == "garmin-activity-1"
    assert health.json()["data"][0]["values"]["body_battery_score"] == 72


def test_garmin_admin_token_import_requires_admin_token_and_redacts_session_payload(monkeypatch) -> None:
    from tests.unit.api_test_helpers import create_sqlite_test_client

    monkeypatch.setenv("JOHNNY_ADMIN_TOKEN", "admin-secret")
    client = create_sqlite_test_client()
    connected = _connect_api_garmin(
        client,
        provider_account_id="garmin-account-admin-import-api",
        with_profile=True,
    )

    unauthorized = client.post(
        f"/api/v1/integrations/connections/{connected['id']}/admin-token-import",
        headers={"X-Johnny-User-Id": "user-1"},
        json={"session_payload": '{"oauth2_token":"manual-secret-token"}'},
    )
    response = client.post(
        f"/api/v1/integrations/connections/{connected['id']}/admin-token-import",
        headers={"X-Johnny-User-Id": "user-1", "X-Johnny-Admin-Token": "admin-secret"},
        json={"session_payload": '{"oauth2_token":"manual-secret-token"}'},
    )

    assert unauthorized.status_code == 401
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "active"
    assert data["credential_status"] == "active"
    assert data["credential_format"] == "garminconnect-session-json"
    assert "encrypted_payload" not in data
    assert "manual-secret-token" not in response.text
    assert "admin-secret" not in response.text


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


def test_garmin_connect_endpoint_reports_missing_credential_cipher_without_echoing_credentials(monkeypatch) -> None:
    from tests.unit.api_test_helpers import create_sqlite_test_client

    monkeypatch.delenv("GARMIN_CREDENTIAL_MASTER_KEY", raising=False)
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
        "message": "Garmin credential encryption is not configured",
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


def _put_api_athlete_profile(client) -> None:  # noqa: ANN001
    response = client.put(
        "/api/v1/athlete/profile",
        headers={"X-Johnny-User-Id": "user-1"},
        json={
            "timezone": "Asia/Taipei",
            "experience_level": "intermediate",
            "current_weekly_mileage_km": 42,
            "preferred_training_days": ["tuesday", "thursday", "sunday"],
            "preferred_long_run_day": "sunday",
            "max_runs_per_week": 4,
        },
    )
    assert response.status_code == 200


def _connect_api_garmin(
    client,  # noqa: ANN001
    *,
    provider_account_id: str,
    user_id: str = "user-1",
    email: str = "runner@example.com",
    resource_adapter=None,  # noqa: ANN001
    with_profile: bool = False,
) -> dict:
    from src.api.routes.integrations import get_garmin_credential_cipher, get_garmin_login_adapter, get_garmin_resource_adapter
    from src.application.integrations import GarminAccountProfile

    if with_profile:
        _put_api_athlete_profile(client)
    adapter = resource_adapter or _ApiFakeGarminResourceAdapter()
    client.app.dependency_overrides[get_garmin_login_adapter] = lambda: _ApiFakeGarminLoginAdapter(
        GarminAccountProfile(
            provider_account_id=provider_account_id,
            display_name="Garmin Runner",
            session_payload='{"oauth2_token":"secret-token"}',
        )
    )
    client.app.dependency_overrides[get_garmin_credential_cipher] = lambda: _ApiFakeCipher()
    client.app.dependency_overrides[get_garmin_resource_adapter] = lambda: adapter
    response = client.post(
        "/api/v1/integrations/garmin/connect",
        headers={"X-Johnny-User-Id": user_id},
        json={"email": email, "password": "garmin-password", "region": "global"},
    )
    assert response.status_code == 200
    return response.json()["data"]


class _ApiFakeCipher:
    key_id = "local-fernet"

    def encrypt(self, plaintext: str) -> str:
        assert plaintext in {'{"oauth2_token":"secret-token"}', '{"oauth2_token":"manual-secret-token"}'}
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


class _ApiFakeGarminCredentialBlockedResourceAdapter:
    def __init__(self) -> None:
        self.calls = 0

    def fetch_resource(self, *, connection, resource_type, start_date, end_date, timezone_name, cursor):
        from src.application.integrations import GarminCredentialBlockedError

        self.calls += 1
        raise GarminCredentialBlockedError("session cookie=session-secret expired")


class _ApiFakeGarminZeroItemPartialFailureResourceAdapter:
    def fetch_resource(self, *, connection, resource_type, start_date, end_date, timezone_name, cursor):
        from src.application.integrations import GarminResourceFetchResult

        if resource_type == "body_battery":
            raise RuntimeError('{"sid":"abc-session"}')
        return GarminResourceFetchResult(items=[], cursor={"date": end_date.isoformat()})


class _ApiBlockingGarminResourceAdapter:
    def __init__(self) -> None:
        from threading import Event

        self.entered = Event()
        self.release = Event()

    def fetch_resource(self, *, connection, resource_type, start_date, end_date, timezone_name, cursor):
        from src.application.integrations import GarminResourceFetchResult

        if resource_type == "activities":
            self.entered.set()
            assert self.release.wait(timeout=5)
        return GarminResourceFetchResult(items=[], cursor={"date": end_date.isoformat()})
