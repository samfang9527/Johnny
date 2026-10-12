from datetime import date, datetime, timezone

from src.application.daily_advice_context import (
    load_week_execution,
    plan_week_for_date,
    resolve_plan_for_date,
)
from src.domain.activity_health import CompletedActivity
from src.domain.training_plan import TrainingPlan, Workout


class PlanStore:
    def __init__(self, current: TrainingPlan, previous: TrainingPlan | None = None) -> None:
        self.current = current
        self.previous = previous

    def get_current_plan_for_user(self, user_id: str) -> TrainingPlan | None:
        return self.current if user_id == self.current.user_id else None

    def get_plan_for_user(self, user_id: str, plan_id: str | None) -> TrainingPlan | None:
        return self.previous if self.previous and user_id == self.previous.user_id and plan_id == self.previous.id else None


class ActivityStore:
    def __init__(self, activities: tuple[CompletedActivity, ...]) -> None:
        self.activities = activities
        self.queries: list[tuple[date, date]] = []

    def list_activities_for_user_between(self, user_id: str, start: date, end: date, *, limit=None, offset=0):
        self.queries.append((start, end))
        return [
            activity
            for activity in self.activities
            if activity.user_id == user_id and start <= activity.started_at.date() <= end
        ]


def _plan(start: date, end: date, *, workouts: tuple[Workout, ...] = (), **kwargs) -> TrainingPlan:
    return TrainingPlan.create(user_id="athlete", name="Plan", starts_on=start, ends_on=end, workouts=workouts, **kwargs)


def _workout(day: date, *, id: str = "workout") -> Workout:
    return Workout.create(id=id, scheduled_for=day, workout_type="easy_run", purpose="Aerobic base", planned_duration_minutes=40)


def _run(started_at: datetime, *, duration_minutes: int = 40) -> CompletedActivity:
    return CompletedActivity.create(
        user_id="athlete",
        source="manual",
        started_at=started_at,
        sport_type="run",
        distance_meters=8_000,
        duration_seconds=duration_minutes * 60,
    )


def test_plan_week_uses_plan_start_instead_of_calendar_monday_and_caps_last_block() -> None:
    plan = _plan(date(2026, 10, 7), date(2026, 10, 18))

    assert plan_week_for_date(plan, date(2026, 10, 8)) == (date(2026, 10, 7), date(2026, 10, 13))
    assert plan_week_for_date(plan, date(2026, 10, 15)) == (date(2026, 10, 14), date(2026, 10, 18))


def test_plan_for_date_uses_predecessor_until_new_projection_starts() -> None:
    previous = _plan(date(2026, 10, 7), date(2026, 10, 13), status="superseded", id="previous")
    current = _plan(
        date(2026, 10, 14), date(2026, 10, 27), id="current", metadata={"previous_plan_id": "previous"}
    )
    store = PlanStore(current, previous)

    assert resolve_plan_for_date(store, "athlete", date(2026, 10, 12)) == previous
    assert resolve_plan_for_date(store, "athlete", date(2026, 10, 15)) == current
    assert resolve_plan_for_date(store, "athlete", date(2026, 10, 28)) is None
    assert resolve_plan_for_date(store, "another-athlete", date(2026, 10, 12)) is None


def test_loader_reads_prior_utc_day_to_include_activity_on_first_local_week_day() -> None:
    plan = _plan(date(2026, 10, 7), date(2026, 10, 13), workouts=(_workout(date(2026, 10, 7)),))
    store = ActivityStore((_run(datetime(2026, 10, 6, 16, tzinfo=timezone.utc)),))

    result = load_week_execution(
        training_data=store, plan=plan, user_id="athlete", anchor_date=date(2026, 10, 7),
        as_of=datetime(2026, 10, 7, 4, tzinfo=timezone.utc), timezone_name="Asia/Tokyo",
        activity_coverage_complete=True,
    )

    assert store.queries == [(date(2026, 10, 6), date(2026, 10, 14))]
    assert result.completed_count == 1
    assert result.today_completed is True
    assert result.actual_minutes == 40


def test_loader_excludes_activity_from_prior_local_day_despite_utc_week_date() -> None:
    plan = _plan(date(2026, 10, 7), date(2026, 10, 13), workouts=(_workout(date(2026, 10, 7)),))
    store = ActivityStore((
        _run(datetime(2026, 10, 7, 3, tzinfo=timezone.utc), duration_minutes=50),
        _run(datetime(2026, 10, 8, 6, tzinfo=timezone.utc), duration_minutes=40),
    ))

    result = load_week_execution(
        training_data=store, plan=plan, user_id="athlete", anchor_date=date(2026, 10, 8),
        as_of=datetime(2026, 10, 8, 7, tzinfo=timezone.utc), timezone_name="America/Los_Angeles",
        activity_coverage_complete=True,
    )

    assert result.completed_count == 1
    assert result.actual_minutes == 40
    assert result.extra_count == 0
