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

    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == "validation_error"
    assert valid.status_code == 200
    assert valid.json()["data"]["run_ref"].startswith("conversation-run-")


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
