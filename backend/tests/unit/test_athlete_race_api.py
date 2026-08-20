from datetime import date

from fastapi.testclient import TestClient

from tests.unit.api_test_helpers import create_sqlite_test_client


def test_athlete_profile_routes_save_and_load_current_user_profile() -> None:
    client = _client()

    response = client.put(
        "/api/athlete/profile",
        headers={"X-Johnny-User-Id": "user-1"},
        json={
            "timezone": "Asia/Taipei",
            "experience_level": "intermediate",
            "current_weekly_mileage": 42.5,
            "preferred_training_days": ["tuesday", "thursday", "sunday"],
            "preferred_long_run_day": "sunday",
            "max_runs_per_week": 4,
            "unit_preference": "metric",
            "training_preferences": {"surface": "road"},
            "injury_notes": "Left calf watch",
        },
    )

    assert response.status_code == 200
    assert response.json()["data"] == {
        "id": response.json()["data"]["id"],
        "user_id": "user-1",
        "timezone": "Asia/Taipei",
        "experience_level": "intermediate",
        "current_weekly_mileage": 42.5,
        "preferred_training_days": ["tuesday", "thursday", "sunday"],
        "preferred_long_run_day": "sunday",
        "max_runs_per_week": 4,
        "unit_preference": "metric",
        "training_preferences": {"surface": "road"},
        "injury_notes": "Left calf watch",
    }

    loaded = client.get("/api/athlete/profile", headers={"X-Johnny-User-Id": "user-1"})

    assert loaded.status_code == 200
    assert loaded.json()["data"]["timezone"] == "Asia/Taipei"


def test_race_routes_create_update_detail_and_list_with_tenant_scope_and_filters() -> None:
    client = _client()
    first = client.post(
        "/api/races",
        headers={"X-Johnny-User-Id": "user-1"},
        json={
            "name": "Spring Half",
            "race_date": "2027-04-12",
            "distance_meters": 21097,
            "target_finish_seconds": 7200,
            "priority": "primary",
        },
    ).json()["data"]
    client.post(
        "/api/races",
        headers={"X-Johnny-User-Id": "user-1"},
        json={"name": "Tune Up 10K", "race_date": "2027-03-10", "distance_meters": 10000, "priority": "tune_up"},
    )
    client.post(
        "/api/races",
        headers={"X-Johnny-User-Id": "user-2"},
        json={"name": "Other Race", "race_date": "2027-03-11", "distance_meters": 5000},
    )

    updated = client.put(
        f"/api/races/{first['id']}",
        headers={"X-Johnny-User-Id": "user-1"},
        json={**first, "name": "Spring Half Updated", "status": "active"},
    )
    listed = client.get(
        "/api/races?race_date_from=2027-03-01&race_date_to=2027-04-01&limit=1&offset=0",
        headers={"X-Johnny-User-Id": "user-1"},
    )
    hidden = client.get(f"/api/races/{first['id']}", headers={"X-Johnny-User-Id": "user-2"})

    assert updated.status_code == 200
    assert updated.json()["data"]["name"] == "Spring Half Updated"
    assert listed.status_code == 200
    assert [race["name"] for race in listed.json()["data"]] == ["Tune Up 10K"]
    assert hidden.status_code == 404
    assert hidden.json()["error"]["code"] == "not_found"


def _client() -> TestClient:
    return create_sqlite_test_client()
