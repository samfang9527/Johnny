from tests.unit.api_test_helpers import create_sqlite_test_client


def test_training_plan_routes_create_load_and_update_workout_status_with_tenant_scope() -> None:
    client = create_sqlite_test_client()
    created = client.post(
        "/api/v1/training-plans",
        headers={"X-Johnny-User-Id": "user-1"},
        json={
            "name": "Half Marathon Build",
            "starts_on": "2027-01-01",
            "ends_on": "2027-03-31",
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

    assert created.status_code == 200
    plan = created.json()["data"]
    workout_id = plan["workouts"][0]["id"]
    detail = client.get(f"/api/v1/training-plans/{plan['id']}", headers={"X-Johnny-User-Id": "user-1"})
    listed = client.get("/api/v1/training-plans?limit=10&offset=0", headers={"X-Johnny-User-Id": "user-1"})
    hidden = client.get(f"/api/v1/training-plans/{plan['id']}", headers={"X-Johnny-User-Id": "user-2"})
    updated = client.patch(
        f"/api/v1/training-plans/{plan['id']}/workouts/{workout_id}",
        headers={"X-Johnny-User-Id": "user-1"},
        json={"status": "completed"},
    )

    assert detail.status_code == 200
    assert detail.json()["data"]["name"] == "Half Marathon Build"
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()["data"]] == [plan["id"]]
    assert hidden.status_code == 404
    assert updated.status_code == 200
    assert updated.json()["data"]["workouts"][0]["status"] == "completed"


def test_training_plan_routes_accept_and_return_structured_workout_details() -> None:
    client = create_sqlite_test_client()

    created = client.post(
        "/api/v1/training-plans",
        headers={"X-Johnny-User-Id": "user-1"},
        json={
            "name": "Detailed Build",
            "starts_on": "2027-01-01",
            "ends_on": "2027-01-31",
            "metadata": {
                "plan_series_id": "series-1",
                "previous_plan_id": "plan-old",
                "version": 2,
            },
            "workouts": [
                {
                    "scheduled_for": "2027-01-05",
                    "workout_type": "interval",
                    "purpose": "Improve 5K-specific aerobic power",
                    "planned_duration_minutes": 55,
                    "phase": "build",
                    "coach_note": "Keep the first two reps controlled.",
                    "steps": [
                        {"type": "warmup", "duration_seconds": 900, "target": {"kind": "rpe", "rpe": 3}},
                        {
                            "type": "repeat",
                            "repeat_count": 4,
                            "steps": [
                                {
                                    "type": "work",
                                    "distance_meters": 800,
                                    "target": {
                                        "kind": "pace",
                                        "zone": "interval",
                                        "pace_range_seconds_per_km": [275, 285],
                                        "rpe": 8,
                                    },
                                },
                                {
                                    "type": "recovery",
                                    "distance_meters": 400,
                                    "target": {"kind": "pace", "zone": "easy", "rpe": 3},
                                },
                            ],
                        },
                        {"type": "cooldown", "duration_seconds": 600, "target": {"kind": "rpe", "rpe": 2}},
                    ],
                }
            ],
        },
    )

    assert created.status_code == 200
    plan = created.json()["data"]
    workout = plan["workouts"][0]
    assert plan["metadata"]["plan_series_id"] == "series-1"
    assert workout["phase"] == "build"
    assert workout["coach_note"] == "Keep the first two reps controlled."
    assert workout["compact_summary"] == "暖身 15 分鐘 ＋ 4 組（主課表・間歇配速 800 公尺／組間恢復・輕鬆配速 400 公尺） ＋ 緩和 10 分鐘"
    assert workout["steps"][1]["repeat_count"] == 4


def test_activity_and_health_routes_create_and_list_current_user_data() -> None:
    client = create_sqlite_test_client()
    activity = client.post(
        "/api/v1/activities",
        headers={"X-Johnny-User-Id": "user-1"},
        json={
            "source": "manual",
            "started_at": "2027-01-02T07:00:00Z",
            "sport_type": "running",
            "distance_meters": 5000,
            "duration_seconds": 1500,
            "average_heart_rate": 145,
        },
    )
    client.post(
        "/api/v1/health-metrics/daily",
        headers={"X-Johnny-User-Id": "user-1"},
        json={
            "metric_date": "2027-01-02",
            "source": "manual",
            "sleep_duration_minutes": 480,
            "hrv_ms": 55,
            "hrv_baseline_ms": 52,
            "resting_heart_rate": 48,
            "body_battery_score": 74,
        },
    )

    activities = client.get(
        "/api/v1/activities?started_on_or_after=2027-01-01&started_on_or_before=2027-01-03&limit=10&offset=0",
        headers={"X-Johnny-User-Id": "user-1"},
    )
    hidden = client.get("/api/v1/activities", headers={"X-Johnny-User-Id": "user-2"})
    health = client.get(
        "/api/v1/health-metrics/daily?measured_on_or_after=2027-01-01&measured_on_or_before=2027-01-03",
        headers={"X-Johnny-User-Id": "user-1"},
    )

    assert activity.status_code == 200
    assert activity.json()["data"]["average_pace_seconds_per_km"] == 300
    assert activities.status_code == 200
    assert [item["source"] for item in activities.json()["data"]] == ["manual"]
    assert hidden.json()["data"] == []
    assert health.status_code == 200
    assert health.json()["data"][0]["values"]["hrv_ms"] == 55
    assert health.json()["data"][0]["values"]["body_battery_score"] == 74
