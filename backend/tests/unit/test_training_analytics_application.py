from datetime import date, datetime, timezone

from src.application.training_analytics import TodayContextService
from src.domain.activity_health import CompletedActivity, DailyHealthMetrics
from src.domain.training_plan import TrainingPlan, Workout


ANCHOR = date(2027, 1, 28)


class FakeActivityRepository:
    def __init__(
        self,
        *,
        activities: tuple[CompletedActivity, ...] = (),
        health_metrics: tuple[DailyHealthMetrics, ...] = (),
    ) -> None:
        self.activities = activities
        self.health_metrics = health_metrics

    def list_activities_for_user_between(
        self,
        user_id: str,
        started_on_or_after: date,
        started_on_or_before: date,
        *,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[CompletedActivity]:
        results = [
            activity
            for activity in self.activities
            if started_on_or_after <= activity.started_at.date() <= started_on_or_before
        ]
        return results[offset : offset + limit if limit is not None else None]

    def list_daily_health_metrics_for_user_between(
        self,
        user_id: str,
        measured_on_or_after: date,
        measured_on_or_before: date,
        *,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[DailyHealthMetrics]:
        results = [
            metric
            for metric in self.health_metrics
            if measured_on_or_after <= metric.metric_date <= measured_on_or_before
        ]
        return results[offset : offset + limit if limit is not None else None]


class FakeTrainingPlanRepository:
    def __init__(self, plan: TrainingPlan | None) -> None:
        self.plan = plan

    def get_current_plan_for_user(self, user_id: str) -> TrainingPlan | None:
        return self.plan


def _activity(
    *,
    user_id: str = "user-1",
    activity_date: date = ANCHOR,
    distance_meters: float = 8_000,
    duration_seconds: int = 2_400,
) -> CompletedActivity:
    return CompletedActivity.create(
        user_id=user_id,
        source="manual",
        started_at=datetime(activity_date.year, activity_date.month, activity_date.day, 7, 30, tzinfo=timezone.utc),
        sport_type="run",
        distance_meters=distance_meters,
        duration_seconds=duration_seconds,
    )


def _health(
    *,
    user_id: str = "user-1",
    metric_date: date = ANCHOR,
    sleep_duration_minutes: float | None = 500,
    hrv_ms: float | None = 55,
    hrv_baseline_ms: float | None = 50,
    resting_heart_rate: float | None = 48,
    stress_score: float | None = 20,
) -> DailyHealthMetrics:
    return DailyHealthMetrics.create(
        user_id=user_id,
        metric_date=metric_date,
        sleep_duration_minutes=sleep_duration_minutes,
        hrv_ms=hrv_ms,
        hrv_baseline_ms=hrv_baseline_ms,
        resting_heart_rate=resting_heart_rate,
        stress_score=stress_score,
    )


def _plan(user_id: str = "user-1") -> TrainingPlan:
    return TrainingPlan.create(
        user_id=user_id,
        name="Build Plan",
        starts_on=date(2027, 1, 1),
        ends_on=date(2027, 2, 28),
        workouts=(
            Workout.create(
                id="workout-today",
                scheduled_for=ANCHOR,
                workout_type="easy_run",
                purpose="Aerobic base",
                planned_duration_minutes=45,
                planned_distance_meters=8_000,
            ),
            Workout.create(
                id="workout-tomorrow",
                scheduled_for=date(2027, 1, 29),
                workout_type="rest",
                purpose="Absorb training",
                planned_duration_minutes=1,
            ),
        ),
    )


def test_today_context_aggregates_plan_activity_health_and_metrics_without_prose() -> None:
    service = TodayContextService(
        activity_repository=FakeActivityRepository(
            activities=(
                _activity(activity_date=ANCHOR, distance_meters=8_000, duration_seconds=2_400),
                    _activity(activity_date=date(2027, 1, 22), distance_meters=4_000, duration_seconds=1_200),
            ),
            health_metrics=(
                _health(metric_date=date(2027, 1, 25), resting_heart_rate=47),
                _health(metric_date=ANCHOR),
            ),
        ),
        training_plan_repository=FakeTrainingPlanRepository(_plan()),
    )

    context = service.build(user_id="user-1", anchor_date=ANCHOR)
    payload = context.to_payload()

    assert [workout["id"] for workout in context.scheduled_workouts] == ["workout-today"]
    assert [activity["distance_meters"] for activity in context.recent_activities] == [8_000, 4_000]
    assert context.training_load.weekly_distance_meters == 12_000
    assert context.recovery.evidence["hrv"]["level"] == "ready"
    assert context.recovery.resting_heart_rate_baseline == 47
    assert "recommendation" not in payload
    assert "coaching_text" not in payload


def test_today_context_excludes_cross_user_data_even_when_repository_leaks_it() -> None:
    service = TodayContextService(
        activity_repository=FakeActivityRepository(
            activities=(
                _activity(user_id="user-1", activity_date=ANCHOR, distance_meters=5_000),
                _activity(user_id="user-2", activity_date=ANCHOR, distance_meters=50_000),
            ),
            health_metrics=(
                _health(user_id="user-1", metric_date=date(2027, 1, 25), resting_heart_rate=48),
                _health(user_id="user-1", metric_date=ANCHOR, resting_heart_rate=49, stress_score=None),
                _health(user_id="user-2", metric_date=ANCHOR, sleep_duration_minutes=240, stress_score=99),
            ),
        ),
        training_plan_repository=FakeTrainingPlanRepository(_plan(user_id="user-2")),
    )

    context = service.build(user_id="user-1", anchor_date=ANCHOR)

    assert context.scheduled_workouts == ()
    assert [activity["user_id"] for activity in context.recent_activities] == ["user-1"]
    assert context.training_load.weekly_distance_meters == 5_000
    assert context.recovery.stress_score is None
