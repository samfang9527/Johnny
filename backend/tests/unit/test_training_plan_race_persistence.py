from datetime import date

from src.domain.training_plan import TrainingPlan, Workout, WorkoutStep, WorkoutTarget
from src.infrastructure.database.models import Base, UserModel
from src.infrastructure.database.training_plan_repository import SqlAlchemyTrainingPlanRepository


def test_race_workout_and_target_evidence_survive_sqlite_round_trip(sqlite_session_factory) -> None:
    Base.metadata.create_all(sqlite_session_factory.kw["bind"])
    with sqlite_session_factory() as session:
        user = UserModel(email="race-roundtrip@example.com", display_name="Runner")
        session.add(user)
        session.flush()
        saved = SqlAlchemyTrainingPlanRepository(session).save_plan(
            user.id,
            TrainingPlan.create(
                user_id=user.id,
                name="Race plan",
                starts_on=date(2027, 2, 1),
                ends_on=date(2027, 2, 7),
                workouts=(
                    Workout.create(
                        scheduled_for=date(2027, 2, 7),
                        workout_type="race",
                        purpose="Controlled tune-up",
                        planned_distance_meters=10_000,
                        race_goal_id="race-1",
                        race_name="Taipei 10K",
                        race_priority="tune_up",
                        steps=(
                            WorkoutStep.create(
                                step_type="free_run",
                                distance_meters=10_000,
                                target=WorkoutTarget(
                                    kind="rpe",
                                    zone="marathon",
                                    rpe=6,
                                    pace_range_seconds_per_km=(350, 400),
                                    pace_source="goal_time",
                                    confidence="low",
                                ),
                            ),
                        ),
                    ),
                ),
            ),
        )
        session.commit()
    with sqlite_session_factory() as session:
        loaded = SqlAlchemyTrainingPlanRepository(session).get_plan_for_user(user.id, saved.id)
        assert loaded is not None
        race = loaded.workouts[0]
        assert (race.race_goal_id, race.race_name, race.race_priority) == ("race-1", "Taipei 10K", "tune_up")
        assert race.planned_duration_minutes is None
        assert race.steps[0].target is not None
        assert race.steps[0].target.pace_source == "goal_time"
