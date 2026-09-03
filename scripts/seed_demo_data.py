from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from src.infrastructure.database.models import (
    ActivityModel,
    AthleteProfileModel,
    Base,
    HealthMetricModel,
    RaceModel,
    RecommendationModel,
    TrainingPlanModel,
    UserModel,
    WorkoutModel,
)
from src.infrastructure.database.session import create_database_engine, create_session_factory, get_database_url


DEMO_USER_ID = "local-user"


def main() -> None:
    database_url = get_database_url()
    engine = create_database_engine(database_url)
    if database_url.startswith("sqlite"):
        Base.metadata.create_all(engine)
    session_factory = create_session_factory(database_url)
    today = date.today()

    with session_factory() as session:
        user = session.get(UserModel, DEMO_USER_ID)
        if user is None:
            user = UserModel(id=DEMO_USER_ID, email="local-user@local.johnny", display_name="Local Runner")
            session.add(user)
            session.flush()

        profile = session.query(AthleteProfileModel).filter_by(user_id=DEMO_USER_ID).one_or_none()
        if profile is None:
            session.add(
                AthleteProfileModel(
                    user_id=DEMO_USER_ID,
                    timezone="Asia/Taipei",
                    experience_level="intermediate",
                    metadata_json={
                        "current_weekly_mileage_km": 42,
                        "preferred_training_days": ["tuesday", "thursday", "saturday", "sunday"],
                        "preferred_long_run_day": "sunday",
                        "max_runs_per_week": 5,
                        "unit_preference": "metric",
                        "training_preferences": {"surface": "road", "interval_style": "time_based"},
                    },
                )
            )

        race = session.query(RaceModel).filter_by(user_id=DEMO_USER_ID, name="Local Half Marathon").one_or_none()
        if race is None:
            race = RaceModel(
                user_id=DEMO_USER_ID,
                name="Local Half Marathon",
                race_date=today + timedelta(days=56),
                distance_meters=21097,
                status="planned",
                metadata_json={"priority": "primary", "target_finish_seconds": 6600},
            )
            session.add(race)
            session.flush()

        plan = session.query(TrainingPlanModel).filter_by(user_id=DEMO_USER_ID, name="Demo Build Block").one_or_none()
        if plan is None:
            plan = TrainingPlanModel(
                user_id=DEMO_USER_ID,
                race_id=race.id,
                name="Demo Build Block",
                status="active",
                starts_on=today - timedelta(days=7),
                ends_on=today + timedelta(days=21),
            )
            session.add(plan)
            session.flush()
            session.add_all(
                [
                    WorkoutModel(
                        training_plan_id=plan.id,
                        scheduled_for=today,
                        workout_type="easy_run",
                        planned_duration_minutes=45,
                        details={
                            "purpose": "Keep aerobic rhythm while checking recovery.",
                            "planned_distance_meters": 8000,
                            "heart_rate_zone": "Z2",
                        },
                    ),
                    WorkoutModel(
                        training_plan_id=plan.id,
                        scheduled_for=today + timedelta(days=2),
                        workout_type="tempo",
                        planned_duration_minutes=50,
                        details={
                            "purpose": "Controlled threshold work if recovery normalizes.",
                            "planned_distance_meters": 9000,
                            "heart_rate_zone": "Z3",
                        },
                    ),
                ]
            )

        started_at = datetime.combine(today - timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc)
        existing_activities = (
            session.query(ActivityModel)
            .filter_by(user_id=DEMO_USER_ID, started_at=started_at, activity_type="running")
            .all()
        )
        if not existing_activities:
            session.add(
                ActivityModel(
                    user_id=DEMO_USER_ID,
                    provider_activity_id=None,
                    started_at=started_at,
                    activity_type="running",
                    distance_meters=6500,
                    duration_seconds=2100,
                    provider_summary={"source": "manual", "average_heart_rate": 142},
                )
            )
        else:
            for existing_activity in existing_activities:
                existing_activity.provider_activity_id = None
                existing_activity.provider_connection_id = None
                existing_activity.provider_summary = {
                    **(existing_activity.provider_summary or {}),
                    "source": "manual",
                    "average_heart_rate": (existing_activity.provider_summary or {}).get("average_heart_rate", 142),
                }

        measured_at = datetime.combine(today, datetime.min.time(), tzinfo=timezone.utc)
        if session.query(HealthMetricModel).filter_by(user_id=DEMO_USER_ID, measured_at=measured_at).count() == 0:
            session.add_all(
                [
                    HealthMetricModel(
                        user_id=DEMO_USER_ID,
                        measured_at=measured_at,
                        metric_type="hrv_ms",
                        value=42,
                        unit="ms",
                        provider_summary={"source": "manual_demo"},
                    ),
                    HealthMetricModel(
                        user_id=DEMO_USER_ID,
                        measured_at=measured_at,
                        metric_type="hrv_baseline_ms",
                        value=51,
                        unit="ms",
                        provider_summary={"source": "manual_demo"},
                    ),
                    HealthMetricModel(
                        user_id=DEMO_USER_ID,
                        measured_at=measured_at,
                        metric_type="sleep_duration_minutes",
                        value=390,
                        unit="minutes",
                        provider_summary={"source": "manual_demo"},
                    ),
                ]
            )

        if session.query(RecommendationModel).filter_by(user_id=DEMO_USER_ID, title="Review today's training context").count() == 0:
            session.add(
                RecommendationModel(
                    user_id=DEMO_USER_ID,
                    title="Review today's training context",
                    rationale="Demo data suggests checking recovery before committing to harder work.",
                    status="pending",
                    evidence={
                        "items": [
                            {
                                "source": "manual_demo",
                                "metric": "hrv_ms",
                                "value": 42,
                                "unit": "ms",
                                "summary": "HRV is below baseline",
                            }
                        ],
                        "proposed_action": {
                            "type": "no_plan_change",
                            "reason": "Use this demo item to test accept/reject/discuss.",
                        },
                        "recommendation": {"type": "informational", "priority": "medium"},
                    },
                )
            )

        session.commit()

    print(f"Seeded Johnny demo data for user {DEMO_USER_ID} on {today.isoformat()}.")


if __name__ == "__main__":
    main()
