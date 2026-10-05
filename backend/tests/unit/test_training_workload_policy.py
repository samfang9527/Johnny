from datetime import date

from src.application.training_workload_policy import (
    CapacitySnapshot, RaceDemand, assess_preparation, build_workload_prescription,
    derive_capacity_snapshot,
)


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


def known_capacity(minutes=240, long=90, confidence="high"):
    return CapacitySnapshot("activities", confidence, minutes, 40, long, date(2026, 12, 28), date(2027, 1, 24), 12, ())


def race(distance=40_000, terrain=None):
    return RaceDemand(distance, date(2027, 4, 26), None, None, None, terrain, None, "complete")


def prescribe(capacity=None, race_demand=None, injury="none", hard=2):
    return build_workload_prescription(
        capacity=capacity or known_capacity(), race=race_demand or race(),
        starts_on=date(2027, 1, 4), ends_on=date(2027, 4, 25),
        phase_segments=[{"phase": "build", "starts_on": "2027-01-04", "ends_on": "2027-04-18"}, {"phase": "taper", "starts_on": "2027-04-19", "ends_on": "2027-04-25"}],
        max_runs_per_week=3, max_hard_sessions_per_week=hard, injury_status=injury,
    )


def test_prescription_progresses_with_cutback_long_run_and_taper_limits():
    weeks = prescribe().weeks
    assert weeks[1].target_minutes <= round(weeks[0].target_minutes * 1.05)
    assert weeks[3].target_minutes == round(weeks[2].target_minutes * 0.85)
    assert weeks[4].target_minutes > weeks[3].target_minutes
    previous = 90
    for week in weeks:
        assert week.long_run_minutes <= round(previous * 1.1)
        assert week.long_run_minutes <= round(week.target_minutes * .5)
        assert week.long_run_minutes <= 180
        previous = week.long_run_minutes
    assert weeks[-1].target_minutes == round(weeks[-2].target_minutes * .65)


def test_injury_holds_reduced_workload_and_terrain_requires_exposure():
    injured = prescribe(injury="current")
    assert max(week.target_minutes for week in injured.weeks) <= round(240 * .8)
    technical = prescribe(race_demand=race(terrain="technical"))
    assert sum(week.terrain_focus for week in technical.weeks[-9:-1]) == 2
    no_hard = prescribe(race_demand=race(terrain="technical"), hard=0)
    assert "terrain_exposure" in no_hard.assessment.factors


def test_assessment_known_gap_precedes_unknown_and_uncalibrated_is_never_on_track():
    gap = assess_preparation(capacity=known_capacity(), race=race(terrain="technical"), starts_on=date(2027, 1, 4), ends_on=date(2027, 4, 25), weekly_minutes=[200, 250], long_run_minutes=[90, 100], terrain_session_count=0, policy_version="race-workload-v1")
    assert gap.status == "gap"
    assert {"weekly_volume", "long_run_endurance", "terrain_exposure"} <= set(gap.factors)
    low = assess_preparation(capacity=known_capacity(confidence="low"), race=race(), starts_on=date(2027, 1, 4), ends_on=date(2027, 4, 25), weekly_minutes=[350], long_run_minutes=[160], terrain_session_count=0, policy_version="race-workload-v1")
    assert low.status == "unknown"
    ultra = assess_preparation(capacity=known_capacity(), race=race(60_000), starts_on=date(2027, 1, 4), ends_on=date(2027, 4, 25), weekly_minutes=[350], long_run_minutes=[160], terrain_session_count=0, policy_version="race-workload-v1")
    assert ultra.status == "unknown"
