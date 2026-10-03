from datetime import date

from fastapi.testclient import TestClient

from tests.unit.api_test_helpers import create_sqlite_test_client


def test_athlete_profile_routes_save_and_load_current_user_profile() -> None:
    client = _client()

    response = client.put(
        "/api/v1/athlete/profile",
        headers={"X-Johnny-User-Id": "user-1"},
        json={
            "timezone": "Asia/Taipei",
            "experience_level": None,
            "current_weekly_mileage_km": 42.5,
            "preferred_training_days": ["tuesday", "thursday", "sunday"],
            "preferred_long_run_day": "sunday",
            "max_runs_per_week": 2,
            "max_hard_sessions_per_week": 1,
            "unit_preference": "metric",
            "training_preferences": {"surface": "road"},
            "injury_status": "recent",
            "injury_areas": ["calf", "quad"],
            "injury_notes": "Left calf watch",
        },
    )

    assert response.status_code == 200
    assert response.json()["data"] == {
        "id": response.json()["data"]["id"],
        "user_id": "user-1",
        "timezone": "Asia/Taipei",
        "experience_level": None,
        "current_weekly_mileage_km": 42.5,
        "preferred_training_days": ["tuesday", "thursday", "sunday"],
        "preferred_long_run_day": "sunday",
        "max_runs_per_week": 2,
        "max_hard_sessions_per_week": 1,
        "unit_preference": "metric",
        "threshold_pace_seconds_per_km": None,
        "training_preferences": {"surface": "road"},
        "injury_status": "recent",
        "injury_areas": ["calf", "quad"],
        "injury_notes": "Left calf watch",
    }

    loaded = client.get("/api/v1/athlete/profile", headers={"X-Johnny-User-Id": "user-1"})

    assert loaded.status_code == 200
    assert loaded.json()["data"]["timezone"] == "Asia/Taipei"
    assert loaded.json()["data"]["current_weekly_mileage_km"] == 42.5
    assert loaded.json()["data"]["max_hard_sessions_per_week"] == 1


def test_athlete_profile_route_preserves_hidden_training_preferences_on_save() -> None:
    client = _client()
    initial = client.put(
        "/api/v1/athlete/profile",
        headers={"X-Johnny-User-Id": "user-1"},
        json={
            "timezone": "Asia/Taipei",
            "experience_level": "beginner",
            "current_weekly_mileage_km": 20,
            "preferred_training_days": ["tuesday"],
            "preferred_long_run_day": "tuesday",
            "max_runs_per_week": 3,
            "unit_preference": "metric",
            "training_preferences": {"surface": "trail", "coach_note": "preserve me"},
            "injury_status": "none",
            "injury_areas": [],
            "injury_notes": None,
        },
    )

    response = client.put(
        "/api/v1/athlete/profile",
        headers={"X-Johnny-User-Id": "user-1"},
        json={
            "timezone": "Asia/Taipei",
            "experience_level": "advanced",
            "current_weekly_mileage_km": 32.5,
            "preferred_training_days": [],
            "preferred_long_run_day": "sunday",
            "max_runs_per_week": 3,
            "unit_preference": "imperial",
            "injury_status": "current",
            "injury_areas": ["other"],
            "injury_notes": "Occasional tightness.",
        },
    )

    assert initial.status_code == 200
    assert response.status_code == 200
    assert response.json()["data"]["training_preferences"] == {"surface": "trail", "coach_note": "preserve me"}
    assert response.json()["data"]["preferred_training_days"] == []


def test_athlete_profile_route_rejects_legacy_unknown_and_other_injury_without_notes() -> None:
    client = _client()

    unknown = client.put(
        "/api/v1/athlete/profile",
        headers={"X-Johnny-User-Id": "user-1"},
        json={
            "timezone": "Asia/Taipei",
            "experience_level": "unknown",
            "current_weekly_mileage_km": 20,
            "preferred_training_days": ["tuesday"],
            "preferred_long_run_day": "tuesday",
            "max_runs_per_week": 3,
            "unit_preference": "metric",
            "injury_status": "none",
            "injury_areas": [],
            "injury_notes": None,
        },
    )
    other_without_notes = client.put(
        "/api/v1/athlete/profile",
        headers={"X-Johnny-User-Id": "user-1"},
        json={
            "timezone": "Asia/Taipei",
            "experience_level": None,
            "current_weekly_mileage_km": 20,
            "preferred_training_days": ["tuesday"],
            "preferred_long_run_day": "tuesday",
            "max_runs_per_week": 3,
            "unit_preference": "metric",
            "injury_status": "current",
            "injury_areas": ["other"],
            "injury_notes": None,
        },
    )

    assert unknown.status_code == 422
    assert other_without_notes.status_code == 422


def test_race_routes_create_update_detail_and_list_with_tenant_scope_and_filters() -> None:
    client = _client()
    first = client.post(
        "/api/v1/races",
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
        "/api/v1/races",
        headers={"X-Johnny-User-Id": "user-1"},
        json={"name": "Tune Up 10K", "race_date": "2027-03-10", "distance_meters": 10000, "priority": "tune_up"},
    )
    client.post(
        "/api/v1/races",
        headers={"X-Johnny-User-Id": "user-2"},
        json={"name": "Other Race", "race_date": "2027-03-11", "distance_meters": 5000},
    )

    updated = client.put(
        f"/api/v1/races/{first['id']}",
        headers={"X-Johnny-User-Id": "user-1"},
        json={
            "name": "Spring Half Updated",
            "race_date": first["race_date"],
            "distance_meters": first["distance_meters"],
            "target_finish_seconds": first["target_finish_seconds"],
            "priority": first["priority"],
            "status": "active",
        },
    )
    listed = client.get(
        "/api/v1/races?race_date_from=2027-03-01&race_date_to=2027-04-01&limit=1&offset=0",
        headers={"X-Johnny-User-Id": "user-1"},
    )
    listed_with_next = client.get("/api/v1/races?limit=1&offset=0", headers={"X-Johnny-User-Id": "user-1"})
    invalid_page = client.get("/api/v1/races?limit=-1&offset=0", headers={"X-Johnny-User-Id": "user-1"})
    hidden = client.get(f"/api/v1/races/{first['id']}", headers={"X-Johnny-User-Id": "user-2"})

    assert updated.status_code == 200
    assert updated.json()["data"]["name"] == "Spring Half Updated"
    assert listed.status_code == 200
    assert [race["name"] for race in listed.json()["data"]] == ["Tune Up 10K"]
    assert listed.json()["paging"] == {"limit": 1, "offset": 0, "has_next": False}
    assert [race["name"] for race in listed_with_next.json()["data"]] == ["Tune Up 10K"]
    assert listed_with_next.json()["paging"] == {"limit": 1, "offset": 0, "has_next": True}
    assert "total_pages" not in listed_with_next.json()["paging"]
    assert invalid_page.status_code == 422
    assert invalid_page.json()["error"]["code"] == "validation_error"
    assert hidden.status_code == 404
    assert hidden.json()["error"]["code"] == "not_found"


def test_race_create_rejects_status_and_unexpected_fields() -> None:
    client = _client()

    with_status = client.post(
        "/api/v1/races",
        headers={"X-Johnny-User-Id": "user-1"},
        json={
            "name": "Spring Half",
            "race_date": "2027-04-12",
            "distance_meters": 21097,
            "priority": "primary",
            "status": "active",
        },
    )
    with_extra = client.post(
        "/api/v1/races",
        headers={"X-Johnny-User-Id": "user-1"},
        json={
            "name": "Spring Half",
            "race_date": "2027-04-12",
            "distance_meters": 21097,
            "priority": "primary",
            "distance_kilometers": 21.097,
        },
    )

    assert with_status.status_code == 422
    assert with_extra.status_code == 422


def test_race_update_accepts_status_but_rejects_unexpected_fields() -> None:
    client = _client()
    race = client.post(
        "/api/v1/races",
        headers={"X-Johnny-User-Id": "user-1"},
        json={
            "name": "Spring Half",
            "race_date": "2027-04-12",
            "distance_meters": 21097,
            "priority": "primary",
        },
    ).json()["data"]

    updated = client.put(
        f"/api/v1/races/{race['id']}",
        headers={"X-Johnny-User-Id": "user-1"},
        json={
            "name": race["name"],
            "race_date": race["race_date"],
            "distance_meters": race["distance_meters"],
            "target_finish_seconds": race["target_finish_seconds"],
            "priority": race["priority"],
            "status": "active",
        },
    )
    with_extra = client.put(
        f"/api/v1/races/{race['id']}",
        headers={"X-Johnny-User-Id": "user-1"},
        json={
            "name": race["name"],
            "race_date": race["race_date"],
            "distance_meters": race["distance_meters"],
            "target_finish_seconds": race["target_finish_seconds"],
            "priority": race["priority"],
            "status": "active",
            "distance_kilometers": 21.097,
        },
    )

    assert updated.status_code == 200
    assert updated.json()["data"]["status"] == "active"
    assert with_extra.status_code == 422


def _client() -> TestClient:
    return create_sqlite_test_client()
