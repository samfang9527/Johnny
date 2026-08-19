from datetime import date, datetime, timezone

from src.domain.activity_health import CompletedActivity, DailyHealthMetrics
from src.domain.training_analytics import TrainingMetricSnapshot
from src.domain.training_plan import TrainingPlan, Workout
from src.infrastructure.database.activity_repository import SqlAlchemyActivityRepository
from src.infrastructure.database.models import Base, UserModel
from src.infrastructure.database.training_metric_snapshot_repository import SqlAlchemyTrainingMetricSnapshotRepository
from src.infrastructure.database.training_plan_repository import SqlAlchemyTrainingPlanRepository
from src.infrastructure.database.uow import SqlAlchemyUnitOfWork


def _activity(*, user_id: str, activity_date: date, distance_meters: float = 5_000) -> CompletedActivity:
    return CompletedActivity.create(
        user_id=user_id,
        source="manual",
        started_at=datetime(activity_date.year, activity_date.month, activity_date.day, 7, 30, tzinfo=timezone.utc),
        sport_type="run",
        distance_meters=distance_meters,
        duration_seconds=1_500,
    )


def _health(*, user_id: str, metric_date: date, resting_heart_rate: float) -> DailyHealthMetrics:
    return DailyHealthMetrics.create(
        user_id=user_id,
        metric_date=metric_date,
        resting_heart_rate=resting_heart_rate,
    )


def test_activity_repository_lists_activities_and_health_metrics_by_user_date_range(sqlite_session_factory) -> None:
    Base.metadata.create_all(sqlite_session_factory.kw["bind"])

    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        owner = UserModel(email="analytics-owner@example.com", display_name="Analytics Owner")
        other = UserModel(email="analytics-other@example.com", display_name="Analytics Other")
        uow.session.add_all([owner, other])
        uow.session.flush()
        repository = SqlAlchemyActivityRepository(uow.session)
        for activity_date, distance_meters in (
            (date(2027, 1, 20), 3_000),
            (date(2027, 1, 22), 4_000),
            (date(2027, 1, 28), 8_000),
        ):
            repository.save_activity(owner.id, _activity(user_id=owner.id, activity_date=activity_date, distance_meters=distance_meters))
        repository.save_activity(other.id, _activity(user_id=other.id, activity_date=date(2027, 1, 28), distance_meters=50_000))
        for metric_date, resting_heart_rate in (
            (date(2027, 1, 20), 47),
            (date(2027, 1, 22), 48),
            (date(2027, 1, 28), 49),
        ):
            repository.save_daily_health_metrics(
                owner.id,
                _health(user_id=owner.id, metric_date=metric_date, resting_heart_rate=resting_heart_rate),
            )
        repository.save_daily_health_metrics(
            other.id,
            _health(user_id=other.id, metric_date=date(2027, 1, 28), resting_heart_rate=99),
        )
        uow.commit()

    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        repository = SqlAlchemyActivityRepository(uow.session)
        activities = repository.list_activities_for_user_between(
            owner.id,
            date(2027, 1, 20),
            date(2027, 1, 28),
            limit=1,
            offset=1,
        )
        health_metrics = repository.list_daily_health_metrics_for_user_between(
            owner.id,
            date(2027, 1, 20),
            date(2027, 1, 28),
            limit=1,
            offset=1,
        )

        assert [activity.distance_meters for activity in activities] == [4_000]
        assert [metric.resting_heart_rate for metric in health_metrics] == [48]


def test_training_metric_snapshot_repository_round_trips_json_and_enforces_ownership(sqlite_session_factory) -> None:
    Base.metadata.create_all(sqlite_session_factory.kw["bind"])

    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        owner = UserModel(email="snapshot-owner@example.com", display_name="Snapshot Owner")
        other = UserModel(email="snapshot-other@example.com", display_name="Snapshot Other")
        uow.session.add_all([owner, other])
        uow.session.flush()
        repository = SqlAlchemyTrainingMetricSnapshotRepository(uow.session)
        older = repository.save_snapshot(
            owner.id,
            TrainingMetricSnapshot.create(
                user_id=owner.id,
                snapshot_type="training_load",
                captured_at=datetime(2027, 1, 28, 9, 0, tzinfo=timezone.utc),
                metrics={
                    "weekly_distance_meters": 12_000,
                    "unavailable_signals": ["mileage_ramp_percentage"],
                },
            ),
        )
        newer = repository.save_snapshot(
            owner.id,
            TrainingMetricSnapshot.create(
                user_id=owner.id,
                snapshot_type="training_load",
                captured_at=datetime(2027, 1, 28, 11, 0, tzinfo=timezone.utc),
                metrics={"weekly_distance_meters": 14_000},
            ),
        )
        repository.save_snapshot(
            owner.id,
            TrainingMetricSnapshot.create(
                user_id=owner.id,
                snapshot_type="recovery_context",
                captured_at=datetime(2027, 1, 28, 10, 0, tzinfo=timezone.utc),
                metrics={"readiness_label": "ready"},
            ),
        )
        repository.save_snapshot(
            other.id,
            TrainingMetricSnapshot.create(
                user_id=other.id,
                snapshot_type="training_load",
                captured_at=datetime(2027, 1, 28, 12, 0, tzinfo=timezone.utc),
                metrics={"weekly_distance_meters": 99_000},
            ),
        )
        uow.commit()

    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        repository = SqlAlchemyTrainingMetricSnapshotRepository(uow.session)
        loaded = repository.get_snapshot_for_user(owner.id, older.id)
        hidden = repository.get_snapshot_for_user(other.id, older.id)
        snapshots = repository.list_snapshots_for_user(owner.id, snapshot_type="training_load")

        assert loaded is not None
        assert loaded.metrics["weekly_distance_meters"] == 12_000
        assert loaded.metrics["unavailable_signals"] == ["mileage_ramp_percentage"]
        assert hidden is None
        assert [snapshot.id for snapshot in snapshots] == [newer.id, older.id]


def test_training_plan_repository_returns_domain_current_plan_for_analytics(sqlite_session_factory) -> None:
    Base.metadata.create_all(sqlite_session_factory.kw["bind"])

    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        user = UserModel(email="analytics-plan@example.com", display_name="Analytics Plan")
        uow.session.add(user)
        uow.session.flush()
        repository = SqlAlchemyTrainingPlanRepository(uow.session)
        repository.save_plan(
            user.id,
            TrainingPlan.create(
                user_id=user.id,
                name="Current Analytics Plan",
                starts_on=date(2027, 1, 1),
                ends_on=date(2027, 2, 28),
                workouts=(
                    Workout.create(
                        scheduled_for=date(2027, 1, 28),
                        workout_type="easy_run",
                        purpose="Aerobic base",
                        planned_duration_minutes=45,
                    ),
                ),
            ),
        )
        uow.commit()

    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        loaded = SqlAlchemyTrainingPlanRepository(uow.session).get_current_plan_for_user(user.id)

        assert loaded is not None
        assert loaded.user_id == user.id
        assert loaded.workouts[0].to_payload()["purpose"] == "Aerobic base"
