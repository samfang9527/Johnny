from datetime import date

from src.application.training_workload_policy import derive_capacity_snapshot


def activity(day: str, *, minutes: int = 60, distance_km: float = 10, sport: str = "run", suffix: str | None = None) -> dict:
    return {
        "id": suffix or day,
        "started_at": f"{day}T07:00:00+08:00",
        "sport_type": sport,
        "duration_seconds": minutes * 60,
        "distance_meters": distance_km * 1000,
    }


def test_capacity_uses_complete_local_weeks_and_deduplicates_running_activities():
    runs = [
        activity("2026-12-28", minutes=40), activity("2026-12-30", minutes=60),
        activity("2027-01-04", minutes=60), activity("2027-01-06", minutes=80),
        activity("2027-01-11", minutes=80), activity("2027-01-13", minutes=100),
        activity("2027-01-18", minutes=100), activity("2027-01-20", minutes=120),
    ]
    runs += [runs[0], activity("2027-01-19", minutes=500, sport="ride")]
    snapshot = derive_capacity_snapshot(profile={"timezone": "Asia/Taipei", "current_weekly_mileage_km": 80}, activities=runs, anchor=date(2027, 1, 28))
    assert snapshot.source == "activities"
    assert snapshot.confidence == "high"
    assert snapshot.weekly_minutes == 160  # median of 100, 140, 180, 220
    assert snapshot.recent_long_run_minutes == 120
    assert snapshot.activity_count == 8
    assert snapshot.observation_start == date(2026, 12, 28)
    assert snapshot.observation_end == date(2027, 1, 24)


def test_capacity_groups_timezone_offsets_in_athlete_local_week():
    runs = [
        activity("2026-12-28", suffix="w1a"), activity("2026-12-30", suffix="w1b"),
        {**activity("2027-01-10", suffix="boundary"), "started_at": "2027-01-11T00:30:00+09:00"},
        activity("2027-01-04", suffix="monday"),
        activity("2027-01-11", suffix="w3a"), activity("2027-01-12", suffix="w3b"),
        activity("2027-01-18", suffix="w4a"), activity("2027-01-19", suffix="w4b"),
    ]
    snapshot = derive_capacity_snapshot(profile={"timezone": "Asia/Taipei"}, activities=runs, anchor=date(2027, 1, 28))
    assert snapshot.confidence == "high"
    assert snapshot.activity_count == 8


def test_capacity_falls_back_to_stated_mileage_when_history_is_insufficient():
    snapshot = derive_capacity_snapshot(profile={"current_weekly_mileage_km": 25}, activities=[activity("2027-01-20")], anchor=date(2027, 1, 28))
    assert snapshot.source == "stated_mileage"
    assert snapshot.confidence == "low"
    assert snapshot.weekly_minutes == 150
    assert snapshot.weekly_distance_km == 25
    assert "activity_history" in snapshot.missing_dimensions


def test_zero_or_missing_mileage_is_missing_not_zero_capacity():
    for profile in ({}, {"current_weekly_mileage_km": 0}):
        snapshot = derive_capacity_snapshot(profile=profile, activities=[], anchor=date(2027, 1, 28))
        assert snapshot.source == "missing"
        assert snapshot.weekly_minutes is None
        assert snapshot.confidence == "low"
