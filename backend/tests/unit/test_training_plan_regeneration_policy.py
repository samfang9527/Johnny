from datetime import date, datetime, timezone

import pytest

from src.application.training_plan_regeneration import RegenerationRequest
from src.domain.agent_runtime import AgentRun
from src.domain.athlete_race import AthleteProfile, RaceGoal
from src.domain.training_plan_regeneration import (
    calculate_regeneration_quota,
    choose_regeneration_strategy,
    decide_regeneration_admission,
)


STARTS_ON = date(2026, 9, 18)


def _race(race_id: str, race_date: date, priority: str = "primary") -> RaceGoal:
    return RaceGoal(
        id=race_id, user_id="athlete-1", name=race_id,
        race_date=race_date, distance_meters=10000, priority=priority,
    )


def _run(run_id: str, status: str, *, request_id: str | None = None,
         finished_at: datetime | None = None, created_plan_id: str | None = None,
         manual: bool = True) -> AgentRun:
    return AgentRun(
        id=run_id, user_id="athlete-1", trigger_type="manual" if manual else "scheduled",
        workflow_name="training_plan_generation", prompt_version="v1", status=status,
        finished_at=finished_at,
        metadata={"manual_regeneration": manual, "client_request_id": request_id,
                  "created_training_plan_id": created_plan_id},
    )


def _profile() -> AthleteProfile:
    return AthleteProfile.create(
        user_id="athlete-1", timezone="Asia/Taipei", experience_level="beginner",
        current_weekly_mileage_km=10, preferred_training_days=("tuesday", "sunday"),
        preferred_long_run_day="sunday", max_runs_per_week=2,
    )


def test_priority_then_date_selects_race_and_window() -> None:
    strategy = choose_regeneration_strategy(
        [_race("secondary", date(2026, 10, 1), "secondary"),
         _race("later-primary", date(2026, 11, 1)),
         _race("earlier-primary", date(2026, 10, 10))],
        starts_on=STARTS_ON, explicit_race_id=None, force_maintenance=False,
    )
    assert (strategy.race_id, strategy.reason, strategy.plan_horizon_weeks) == (
        "earlier-primary", "priority_and_date", 4,
    )


def test_current_future_race_can_override_priority_default() -> None:
    strategy = choose_regeneration_strategy(
        [_race("primary", date(2026, 10, 10)),
         _race("current", date(2026, 10, 1), "secondary")],
        starts_on=STARTS_ON, explicit_race_id="current", force_maintenance=False,
    )
    assert (strategy.race_id, strategy.reason) == ("current", "explicit_race")


def test_explicit_maintenance_ignores_available_races() -> None:
    strategy = choose_regeneration_strategy(
        [_race("future", date(2026, 10, 1))],
        starts_on=STARTS_ON, explicit_race_id=None, force_maintenance=True,
    )
    assert (strategy.race_id, strategy.plan_type, strategy.plan_horizon_weeks) == (
        None, "maintenance", 4,
    )


@pytest.mark.parametrize("races,race_id", [
    ([], "missing"),
    ([_race("expired", date(2026, 9, 17))], "expired"),
])
def test_missing_or_expired_explicit_race_is_not_substituted(races, race_id) -> None:
    strategy = choose_regeneration_strategy(
        races, starts_on=STARTS_ON, explicit_race_id=race_id, force_maintenance=False,
    )
    assert (strategy.race_id, strategy.reason) == (None, "explicit_race_unavailable")


def test_quota_uses_athlete_local_completion_day_at_midnight() -> None:
    quota = calculate_regeneration_quota(
        [_run("before", "completed", finished_at=datetime(2026, 9, 17, 15, 59, tzinfo=timezone.utc), created_plan_id="old"),
         _run("after", "completed", finished_at=datetime(2026, 9, 17, 16, 1, tzinfo=timezone.utc), created_plan_id="new")],
        _profile(), current_instant=datetime(2026, 9, 17, 16, 2, tzinfo=timezone.utc),
        fallback_today=date(2026, 9, 17),
    )
    assert (quota.quota_day, quota.used, quota.remaining, quota.available) == (
        date(2026, 9, 18), 1, 0, False,
    )
    assert quota.next_available_at.isoformat() == "2026-09-19T00:00:00+08:00"


def test_only_successful_manual_activation_consumes_quota() -> None:
    instant = datetime(2026, 9, 17, 2, tzinfo=timezone.utc)
    quota = calculate_regeneration_quota(
        [_run("failed", "failed", finished_at=instant, created_plan_id="p1"),
         _run("no-plan", "completed", finished_at=instant),
         _run("scheduled", "completed", finished_at=instant, created_plan_id="p2", manual=False),
         _run("manual", "completed", finished_at=instant, created_plan_id="p3")],
        _profile(), current_instant=instant, fallback_today=date(2026, 9, 17),
    )
    assert (quota.used, quota.remaining, quota.available) == (1, 0, False)


def test_same_request_reuse_precedes_other_in_flight_run() -> None:
    runs = [_run("in-flight", "queued", request_id="other"),
            _run("original", "failed", request_id="same")]
    quota = calculate_regeneration_quota(
        runs, None, current_instant=datetime(2026, 9, 17, tzinfo=timezone.utc),
        fallback_today=date(2026, 9, 17),
    )
    admission = decide_regeneration_admission(runs, quota, "same")
    assert (admission.action, admission.existing_run) == ("reuse", runs[1])


def test_other_in_flight_run_precedes_exhausted_quota() -> None:
    runs = [_run("in-flight", "started", request_id="other"),
            _run("completed", "completed", finished_at=datetime(2026, 9, 17, 2, tzinfo=timezone.utc), created_plan_id="p")]
    quota = calculate_regeneration_quota(
        runs, None, current_instant=datetime(2026, 9, 17, 3, tzinfo=timezone.utc),
        fallback_today=date(2026, 9, 17),
    )
    admission = decide_regeneration_admission(runs, quota, "new")
    assert (admission.action, admission.existing_run) == ("reuse", runs[0])


def test_exhausted_quota_is_unavailable_without_existing_run() -> None:
    runs = [_run("completed", "completed", finished_at=datetime(2026, 9, 17, 2, tzinfo=timezone.utc), created_plan_id="p")]
    quota = calculate_regeneration_quota(
        runs, None, current_instant=datetime(2026, 9, 17, 3, tzinfo=timezone.utc),
        fallback_today=date(2026, 9, 17),
    )
    admission = decide_regeneration_admission(runs, quota, "new")
    assert (admission.action, admission.existing_run) == ("unavailable", None)


def test_available_quota_admits_queue() -> None:
    quota = calculate_regeneration_quota(
        [], None, current_instant=datetime(2026, 9, 17, tzinfo=timezone.utc),
        fallback_today=date(2026, 9, 17),
    )
    assert decide_regeneration_admission([], quota, "new").action == "queue"


def test_request_value_is_transport_neutral() -> None:
    assert RegenerationRequest("request-1", "race", "race-1").race_id == "race-1"
