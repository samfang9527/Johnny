from datetime import date, datetime, timezone

import pytest

from src.domain.activity_health import CompletedActivity
from src.domain.daily_advice import build_week_execution
from src.domain.training_plan import TrainingPlan, Workout


WEEK_START = date(2026, 10, 7)
ANCHOR = date(2026, 10, 10)
AS_OF = datetime(2026, 10, 10, 4, tzinfo=timezone.utc)


def _workout(day: int, minutes: int = 60, *, id: str | None = None, workout_type: str = "easy_run") -> Workout:
    return Workout.create(
        id=id or f"workout-{day}", scheduled_for=date(2026, 10, day), workout_type=workout_type,
        purpose="Train", planned_duration_minutes=minutes,
    )


def _race(day: int, *, id: str) -> Workout:
    return Workout.create(
        id=id, scheduled_for=date(2026, 10, day), workout_type="race", purpose="Race",
        planned_distance_meters=10_000, race_goal_id=id, race_name="10K", race_priority="tune_up",
    )


def _plan(*workouts: Workout) -> TrainingPlan:
    return TrainingPlan.create(
        user_id="athlete", name="Plan", starts_on=WEEK_START, ends_on=date(2026, 10, 13),
        workouts=tuple(workouts),
    )


def _activity(day: int, minutes: int, *, id: str, match: str | None = None, sport: str = "run") -> CompletedActivity:
    return CompletedActivity.create(
        id=id, user_id="athlete", source="manual", started_at=datetime(2026, 10, day, 2, tzinfo=timezone.utc),
        sport_type=sport, distance_meters=8_000, duration_seconds=minutes * 60, matched_workout_id=match,
    )


def _execution(plan: TrainingPlan, *activities: CompletedActivity, coverage: bool = True):
    return build_week_execution(
        plan, tuple(activities), anchor_date=ANCHOR, as_of=AS_OF,
        timezone_name="UTC", activity_coverage_complete=coverage,
    )


def test_today_and_future_workouts_are_not_missed_at_4am() -> None:
    result = _execution(_plan(_workout(7), _workout(10), _workout(11)))

    assert result.planned_count == 1
    assert result.missed_count == 1
    assert result.planned_minutes == 60
    assert result.today_completed is False


def test_one_same_day_unmatched_run_completes_one_workout() -> None:
    result = _execution(_plan(_workout(7)), _activity(7, 60, id="run-7"))

    assert (result.completed_count, result.missed_count, result.extra_count) == (1, 0, 0)
    assert result.status == "on_plan"


def test_explicit_match_takes_precedence_over_same_day_ambiguity() -> None:
    result = _execution(
        _plan(_workout(7, id="first"), _workout(7, id="second")),
        _activity(7, 60, id="run-7", match="second"),
    )

    assert result.completed_count == 1
    assert result.missed_count == 1
    assert result.extra_count == 0


@pytest.mark.parametrize("workouts,activities", [
    ((_workout(7, id="one"), _workout(7, id="two")), (_activity(7, 60, id="run"),)),
    ((_workout(7),), (_activity(7, 30, id="one"), _activity(7, 30, id="two"))),
])
def test_ambiguous_same_day_runs_neither_complete_nor_miss_a_workout(workouts, activities) -> None:
    result = _execution(_plan(*workouts), *activities)

    assert result.completed_count == 0
    assert result.missed_count == 0
    assert result.extra_count == 0
    assert result.status == "insufficient_evidence"


def test_only_running_load_counts_and_clear_unplanned_run_is_extra() -> None:
    result = _execution(
        _plan(_workout(7, 40)),
        _activity(7, 40, id="planned"),
        _activity(8, 50, id="bike", sport="cycling"),
        _activity(8, 30, id="extra"),
    )

    assert (result.completed_count, result.extra_count) == (1, 1)
    assert (result.planned_minutes, result.actual_minutes) == (40, 70)
    assert result.status == "above"


def test_race_without_prescribed_minutes_does_not_invent_volume_denominator() -> None:
    result = _execution(_plan(_race(7, id="race")), _activity(7, 50, id="race-run", match="race"))

    assert result.completed_count == 1
    assert result.planned_minutes is None
    assert result.status == "insufficient_evidence"


def test_rest_day_is_not_counted_as_missed_running_or_one_planned_minute() -> None:
    result = _execution(_plan(_workout(7, 1, workout_type="rest")))

    assert (result.planned_count, result.missed_count) == (0, 0)
    assert result.planned_minutes is None
    assert result.status == "insufficient_evidence"


@pytest.mark.parametrize("planned,actual,want", [
    (100, 129, "on_plan"),  # >25%, but under 30 minutes
    (100, 130, "above"),    # >25% and exactly 30 minutes
    (120, 150, "on_plan"),  # exactly 25% is insufficient
    (120, 151, "above"),
])
def test_above_plan_requires_both_excess_boundaries(planned: int, actual: int, want: str) -> None:
    result = _execution(_plan(_workout(7, planned)), _activity(7, actual, id="run"))

    assert result.status == want


def test_seconds_below_thirty_minute_excess_do_not_round_up_to_above() -> None:
    nearly_thirty_extra = CompletedActivity.create(
        id="run", user_id="athlete", source="manual",
        started_at=datetime(2026, 10, 7, 2, tzinfo=timezone.utc), sport_type="run",
        distance_meters=8_000, duration_seconds=129 * 60 + 59,
    )

    result = _execution(_plan(_workout(7, 100)), nearly_thirty_extra)

    assert result.actual_minutes == 129
    assert result.status == "on_plan"


def test_one_miss_and_exact_25_percent_30_minute_deficit_is_behind() -> None:
    result = _execution(
        _plan(_workout(7, 60), _workout(8, 60)),
        _activity(8, 90, id="run"),
    )

    assert result.missed_count == 1
    assert (result.planned_minutes, result.actual_minutes) == (120, 90)
    assert result.status == "behind"


def test_two_certain_misses_are_behind_without_comparable_minutes() -> None:
    result = _execution(_plan(_race(7, id="first"), _race(8, id="second")))

    assert result.missed_count == 2
    assert result.planned_minutes is None
    assert result.status == "behind"


def test_missed_workout_and_excess_volume_are_mixed() -> None:
    result = _execution(
        _plan(_workout(7, 60), _workout(8, 60)),
        _activity(8, 160, id="run"),
    )

    assert result.missed_count == 1
    assert result.status == "mixed"


def test_incomplete_coverage_never_infers_a_missed_workout() -> None:
    result = _execution(_plan(_workout(7)), coverage=False)

    assert result.missed_count == 0
    assert result.status == "insufficient_evidence"


def test_today_completed_is_evidenced_without_marking_today_missed() -> None:
    result = _execution(_plan(_workout(10)), _activity(10, 60, id="morning-run"))

    assert result.today_completed is True
    assert result.completed_count == 1
    assert result.missed_count == 0
    assert result.planned_count == 1
