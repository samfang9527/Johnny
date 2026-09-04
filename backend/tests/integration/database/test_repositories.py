from datetime import date, datetime, timezone

import pytest
from sqlalchemy.exc import IntegrityError

from src.domain.activity_health import CompletedActivity, DailyHealthMetrics, match_activity_to_workout
from src.domain.athlete_race import AthletePreferences, AthleteProfile, RaceGoal
from src.domain.training_plan import PlanAdjustmentProposal, TrainingPlan, Workout, WorkoutStep, WorkoutTarget
from src.infrastructure.database.models import (
    ActivityModel,
    AgentContextSourceModel,
    AgentRunModel,
    AgentRunStepModel,
    AuthIdentityModel,
    AthleteProfileModel,
    Base,
    HealthMetricModel,
    IntegrationResourceCursorModel,
    RaceModel,
    TrainingPlanModel,
    UserModel,
    WorkoutModel,
)
from src.infrastructure.database.activity_repository import SqlAlchemyActivityRepository
from src.infrastructure.database.athlete_race_repository import SqlAlchemyAthleteRaceRepository
from src.infrastructure.database.recommendation_repository import SqlAlchemyRecommendationRepository
from src.infrastructure.database.training_plan_repository import SqlAlchemyTrainingPlanRepository
from src.infrastructure.database.user_repository import SqlAlchemyUserRepository
from src.infrastructure.database.uow import SqlAlchemyUnitOfWork


def test_repositories_create_and_load_current_training_plan(sqlite_session_factory) -> None:
    Base.metadata.create_all(sqlite_session_factory.kw["bind"])

    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        user = SqlAlchemyUserRepository(uow.session).create_user(
            email="runner@example.com",
            display_name="Runner",
        )
        race = RaceModel(
            user_id=user.id,
            name="Taipei Half",
            race_date=date(2027, 3, 1),
            distance_meters=21097,
        )
        uow.session.add(race)
        uow.session.flush()

        plans = SqlAlchemyTrainingPlanRepository(uow.session)
        plan = plans.create_plan(
            user_id=user.id,
            race_id=race.id,
            name="Half Marathon Build",
            starts_on=date(2027, 1, 1),
            ends_on=date(2027, 2, 28),
        )
        plans.add_workout(
            training_plan_id=plan.id,
            scheduled_for=date(2027, 1, 2),
            workout_type="easy_run",
            planned_duration_minutes=45,
        )
        uow.commit()

    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        loaded = SqlAlchemyTrainingPlanRepository(uow.session).get_current_plan_for_user(user.id)

        assert loaded is not None
        assert loaded.name == "Half Marathon Build"
        assert [workout.workout_type for workout in loaded.workouts] == ["easy_run"]


def test_training_plan_repository_round_trips_plan_workouts_and_ownership(sqlite_session_factory) -> None:
    Base.metadata.create_all(sqlite_session_factory.kw["bind"])

    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        owner = UserModel(email="plan-owner@example.com", display_name="Plan Owner")
        other = UserModel(email="plan-other@example.com", display_name="Plan Other")
        race = RaceModel(
            user_id=owner.id,
            name="Taipei Half",
            race_date=date(2027, 3, 1),
            distance_meters=21_097,
        )
        uow.session.add_all([owner, other])
        uow.session.flush()
        race.user_id = owner.id
        uow.session.add(race)
        uow.session.flush()
        repository = SqlAlchemyTrainingPlanRepository(uow.session)
        saved = repository.save_plan(
            owner.id,
            TrainingPlan.create(
                user_id=owner.id,
                race_id=race.id,
                name="Half Marathon Build",
                starts_on=date(2027, 1, 1),
                ends_on=date(2027, 3, 1),
                workouts=(
                    Workout.create(
                        scheduled_for=date(2027, 1, 9),
                        workout_type="long_run",
                        purpose="Build endurance",
                        planned_duration_minutes=90,
                        planned_distance_meters=16_000,
                    ),
                    Workout.create(
                        scheduled_for=date(2027, 1, 3),
                        workout_type="easy_run",
                        purpose="Aerobic base",
                        planned_duration_minutes=45,
                        planned_distance_meters=8_000,
                        pace_range_seconds_per_km=(330, 390),
                        heart_rate_zone="z2",
                    ),
                ),
            ),
        )
        uow.commit()

    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        repository = SqlAlchemyTrainingPlanRepository(uow.session)
        loaded = repository.get_plan_for_user(owner.id, saved.id)
        hidden = repository.get_plan_for_user(other.id, saved.id)

        assert loaded is not None
        assert hidden is None
        assert loaded.id == saved.id
        assert loaded.user_id == owner.id
        assert loaded.race_id == race.id
        assert loaded.name == "Half Marathon Build"
        assert [workout.workout_type for workout in loaded.workouts] == ["easy_run", "long_run"]
        assert loaded.workouts[0].purpose == "Aerobic base"
        assert loaded.workouts[0].planned_duration_minutes == 45
        assert loaded.workouts[0].planned_distance_meters == 8_000
        assert loaded.workouts[0].pace_range_seconds_per_km == (330, 390)
        assert loaded.workouts[0].heart_rate_zone == "z2"
        assert loaded.workouts[0].steps[0].step_type == "free_run"
        assert loaded.workouts[0].steps[0].duration_seconds == 45 * 60
        assert loaded.workouts[0].steps[0].distance_meters == 8_000
        assert loaded.workouts[0].steps[0].target is not None
        assert loaded.workouts[0].steps[0].target.zone == "easy"
        stored_workout = uow.session.get(WorkoutModel, loaded.workouts[0].id)
        assert stored_workout.details["steps"] == []


def test_training_plan_repository_round_trips_structured_steps_and_plan_metadata(sqlite_session_factory) -> None:
    Base.metadata.create_all(sqlite_session_factory.kw["bind"])

    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        user = UserModel(email="detailed-plan@example.com", display_name="Detailed Plan")
        uow.session.add(user)
        uow.session.flush()
        repository = SqlAlchemyTrainingPlanRepository(uow.session)
        saved = repository.save_plan(
            user.id,
            TrainingPlan.create(
                user_id=user.id,
                name="Detailed Build",
                starts_on=date(2027, 1, 1),
                ends_on=date(2027, 1, 31),
                metadata={
                    "plan_series_id": "series-1",
                    "previous_plan_id": "plan-old",
                    "version": 2,
                    "continuity_summary": "Continue build phase.",
                },
                workouts=(
                    Workout.create(
                        scheduled_for=date(2027, 1, 5),
                        workout_type="interval",
                        purpose="Improve 5K-specific aerobic power",
                        planned_duration_minutes=55,
                        phase="build",
                        coach_note="Keep the first two reps controlled.",
                        steps=(
                            WorkoutStep.create(
                                step_type="warmup",
                                duration_seconds=900,
                                target=WorkoutTarget.rpe(3),
                            ),
                            WorkoutStep.create(
                                step_type="repeat",
                                repeat_count=4,
                                steps=(
                                    WorkoutStep.create(
                                        step_type="work",
                                        distance_meters=800,
                                        target=WorkoutTarget.pace(
                                            zone="interval",
                                            pace_range_seconds_per_km=(275, 285),
                                            rpe=8,
                                            confidence="high",
                                        ),
                                    ),
                                    WorkoutStep.create(
                                        step_type="recovery",
                                        distance_meters=400,
                                        target=WorkoutTarget.pace(zone="easy", rpe=3),
                                    ),
                                ),
                            ),
                            WorkoutStep.create(
                                step_type="cooldown",
                                duration_seconds=600,
                                target=WorkoutTarget.rpe(2),
                            ),
                        ),
                    ),
                ),
            ),
        )
        uow.commit()

    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        loaded = SqlAlchemyTrainingPlanRepository(uow.session).get_plan_for_user(user.id, saved.id)

        assert loaded is not None
        assert loaded.metadata["plan_series_id"] == "series-1"
        assert loaded.metadata["version"] == 2
        assert loaded.workouts[0].phase == "build"
        assert loaded.workouts[0].coach_note == "Keep the first two reps controlled."
        assert loaded.workouts[0].compact_summary == "15 min warmup + 4 x (800m interval / 400m easy) + 10 min cooldown"
        assert loaded.workouts[0].steps[1].repeat_count == 4


def test_training_plan_repository_persists_workout_statuses(sqlite_session_factory) -> None:
    Base.metadata.create_all(sqlite_session_factory.kw["bind"])

    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        user = UserModel(email="plan-status@example.com", display_name="Plan Status")
        uow.session.add(user)
        uow.session.flush()
        repository = SqlAlchemyTrainingPlanRepository(uow.session)
        saved = repository.save_plan(
            user.id,
            TrainingPlan.create(
                user_id=user.id,
                name="Status Plan",
                starts_on=date(2027, 1, 1),
                ends_on=date(2027, 1, 31),
                workouts=(
                    Workout.create(
                        scheduled_for=date(2027, 1, 3),
                        workout_type="easy_run",
                        purpose="Aerobic base",
                        planned_duration_minutes=45,
                    ).transition_to("completed"),
                ),
            ),
        )
        uow.commit()

    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        loaded = SqlAlchemyTrainingPlanRepository(uow.session).get_plan_for_user(user.id, saved.id)

        assert loaded is not None
        assert loaded.workouts[0].status == "completed"
        assert loaded.workouts[0].purpose == "Aerobic base"


def test_training_plan_repository_creates_draft_and_activates_it_for_race(sqlite_session_factory) -> None:
    Base.metadata.create_all(sqlite_session_factory.kw["bind"])

    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        user = UserModel(email="draft-plan-race@example.com", display_name="Draft Plan Race")
        uow.session.add(user)
        uow.session.flush()
        race = RaceModel(
            user_id=user.id,
            name="Taipei Half",
            race_date=date(2027, 3, 1),
            distance_meters=21_097,
        )
        uow.session.add(race)
        uow.session.flush()
        repository = SqlAlchemyTrainingPlanRepository(uow.session)
        active = repository.save_plan(
            user.id,
            TrainingPlan.create(
                user_id=user.id,
                race_id=race.id,
                name="Current Race Plan",
                starts_on=date(2027, 1, 1),
                ends_on=date(2027, 3, 1),
                workouts=(Workout.create(
                    scheduled_for=date(2027, 1, 3),
                    workout_type="easy_run",
                    purpose="Aerobic base",
                    planned_duration_minutes=45,
                ),),
            ),
        )
        draft = repository.create_draft_plan(
            user.id,
            TrainingPlan.create(
                user_id=user.id,
                race_id=race.id,
                name="Generated Draft",
                starts_on=date(2027, 1, 15),
                ends_on=date(2027, 3, 1),
                status="draft",
                workouts=(Workout.create(
                    scheduled_for=date(2027, 1, 16),
                    workout_type="easy_run",
                    purpose="Aerobic base",
                    planned_duration_minutes=40,
                ),),
            ),
        )
        activated = repository.activate_draft_plan(
            user.id,
            draft.id,
            accepted_at=date(2027, 1, 20),
        )
        uow.commit()

    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        repository = SqlAlchemyTrainingPlanRepository(uow.session)
        old_plan = repository.get_plan_for_user(user.id, active.id)
        new_plan = repository.get_plan_for_user(user.id, draft.id)

        assert activated is not None
        assert new_plan is not None
        assert new_plan.status == "active"
        assert old_plan is not None
        assert old_plan.status == "superseded"


def test_training_plan_repository_creates_active_plan_and_supersedes_same_race(sqlite_session_factory) -> None:
    Base.metadata.create_all(sqlite_session_factory.kw["bind"])

    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        user = UserModel(email="active-plan-race@example.com", display_name="Active Plan Race")
        uow.session.add(user)
        uow.session.flush()
        primary_race = RaceModel(
            user_id=user.id,
            name="Taipei Half",
            race_date=date(2027, 3, 1),
            distance_meters=21_097,
        )
        other_race = RaceModel(
            user_id=user.id,
            name="Tokyo Half",
            race_date=date(2027, 4, 1),
            distance_meters=21_097,
        )
        uow.session.add_all((primary_race, other_race))
        uow.session.flush()
        repository = SqlAlchemyTrainingPlanRepository(uow.session)
        same_race = repository.save_plan(
            user.id,
            TrainingPlan.create(
                user_id=user.id,
                race_id=primary_race.id,
                name="Current Same Race Plan",
                starts_on=date(2027, 1, 1),
                ends_on=date(2027, 3, 1),
            ),
        )
        non_overlapping_same_race = repository.save_plan(
            user.id,
            TrainingPlan.create(
                user_id=user.id,
                race_id=primary_race.id,
                name="Current Same Race Fall Plan",
                starts_on=date(2027, 5, 1),
                ends_on=date(2027, 6, 1),
            ),
        )
        other = repository.save_plan(
            user.id,
            TrainingPlan.create(
                user_id=user.id,
                race_id=other_race.id,
                name="Current Other Race Plan",
                starts_on=date(2027, 1, 1),
                ends_on=date(2027, 4, 1),
            ),
        )

        created = repository.create_active_plan(
            user.id,
            TrainingPlan.create(
                user_id=user.id,
                race_id=primary_race.id,
                name="Generated Active Plan",
                starts_on=date(2027, 1, 15),
                ends_on=date(2027, 3, 1),
                workouts=(Workout.create(
                    scheduled_for=date(2027, 1, 16),
                    workout_type="easy_run",
                    purpose="Aerobic base",
                    planned_duration_minutes=40,
                ),),
            ),
        )
        uow.commit()

    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        repository = SqlAlchemyTrainingPlanRepository(uow.session)
        old_same_race = repository.get_plan_for_user(user.id, same_race.id)
        old_non_overlapping_same_race = repository.get_plan_for_user(user.id, non_overlapping_same_race.id)
        old_other_race = repository.get_plan_for_user(user.id, other.id)
        new_plan = repository.get_plan_for_user(user.id, created.id)

        assert new_plan is not None
        assert new_plan.status == "active"
        assert old_same_race is not None
        assert old_same_race.status == "superseded"
        assert old_non_overlapping_same_race is not None
        assert old_non_overlapping_same_race.status == "active"
        assert old_other_race is not None
        assert old_other_race.status == "active"


def test_training_plan_repository_rejects_expired_or_stale_draft_activation(sqlite_session_factory) -> None:
    Base.metadata.create_all(sqlite_session_factory.kw["bind"])

    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        user = UserModel(email="draft-plan-stale@example.com", display_name="Draft Plan Stale")
        uow.session.add(user)
        uow.session.flush()
        race = RaceModel(
            user_id=user.id,
            name="Taipei Half",
            race_date=date(2027, 3, 1),
            distance_meters=21_097,
        )
        uow.session.add(race)
        uow.session.flush()
        repository = SqlAlchemyTrainingPlanRepository(uow.session)
        expired = repository.create_draft_plan(
            user.id,
            TrainingPlan.create(
                user_id=user.id,
                race_id=race.id,
                name="Expired Draft",
                starts_on=date(2027, 1, 1),
                ends_on=date(2027, 3, 1),
                status="draft",
            ),
        )
        stale = repository.create_draft_plan(
            user.id,
            TrainingPlan.create(
                user_id=user.id,
                race_id=race.id,
                name="Stale Draft",
                starts_on=date(2027, 1, 1),
                ends_on=date(2027, 3, 1),
                status="draft",
            ),
        )
        active = repository.save_plan(
            user.id,
            TrainingPlan.create(
                user_id=user.id,
                race_id=race.id,
                name="Newer Active Plan",
                starts_on=date(2027, 1, 15),
                ends_on=date(2027, 3, 1),
            ),
        )
        active_model = uow.session.get(TrainingPlanModel, active.id)
        active_model.created_at = datetime(2027, 1, 20, tzinfo=timezone.utc)

        expired_result = repository.activate_draft_plan(user.id, expired.id, accepted_at=date(2027, 3, 2))
        stale_result = repository.activate_draft_plan(
            user.id,
            stale.id,
            accepted_at=date(2027, 1, 21),
            conflict_created_after=datetime(2027, 1, 19, tzinfo=timezone.utc),
        )
        uow.commit()

    assert expired_result is None
    assert stale_result is None
def test_training_plan_repository_activates_base_plan_and_supersedes_overlaps(sqlite_session_factory) -> None:
    Base.metadata.create_all(sqlite_session_factory.kw["bind"])

    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        user = UserModel(email="draft-plan-base@example.com", display_name="Draft Plan Base")
        uow.session.add(user)
        uow.session.flush()
        repository = SqlAlchemyTrainingPlanRepository(uow.session)
        overlapping = repository.save_plan(
            user.id,
            TrainingPlan.create(
                user_id=user.id,
                name="Current Base Plan",
                starts_on=date(2027, 1, 1),
                ends_on=date(2027, 2, 28),
                workouts=(Workout.create(
                    scheduled_for=date(2027, 1, 3),
                    workout_type="easy_run",
                    purpose="Aerobic base",
                    planned_duration_minutes=45,
                ),),
            ),
        )
        separate = repository.save_plan(
            user.id,
            TrainingPlan.create(
                user_id=user.id,
                name="Later Base Plan",
                starts_on=date(2027, 5, 1),
                ends_on=date(2027, 6, 1),
                workouts=(Workout.create(
                    scheduled_for=date(2027, 5, 3),
                    workout_type="easy_run",
                    purpose="Aerobic base",
                    planned_duration_minutes=45,
                ),),
            ),
        )
        draft = repository.create_draft_plan(
            user.id,
            TrainingPlan.create(
                user_id=user.id,
                name="Generated Base Draft",
                starts_on=date(2027, 2, 1),
                ends_on=date(2027, 3, 31),
                status="draft",
                workouts=(Workout.create(
                    scheduled_for=date(2027, 2, 3),
                    workout_type="easy_run",
                    purpose="Aerobic base",
                    planned_duration_minutes=35,
                ),),
            ),
        )

        assert repository.activate_draft_plan(user.id, draft.id, accepted_at=date(2027, 2, 1)) is not None
        uow.commit()

    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        repository = SqlAlchemyTrainingPlanRepository(uow.session)

        assert repository.get_plan_for_user(user.id, draft.id).status == "active"
        assert repository.get_plan_for_user(user.id, overlapping.id).status == "superseded"
        assert repository.get_plan_for_user(user.id, separate.id).status == "active"


def test_training_plan_repository_round_trips_adjustment_proposals_and_ownership(sqlite_session_factory) -> None:
    Base.metadata.create_all(sqlite_session_factory.kw["bind"])

    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        owner = UserModel(email="proposal-owner@example.com", display_name="Proposal Owner")
        other = UserModel(email="proposal-other@example.com", display_name="Proposal Other")
        uow.session.add_all([owner, other])
        uow.session.flush()
        repository = SqlAlchemyTrainingPlanRepository(uow.session)
        saved_plan = repository.save_plan(
            owner.id,
            TrainingPlan.create(
                user_id=owner.id,
                name="Proposal Plan",
                starts_on=date(2027, 1, 1),
                ends_on=date(2027, 1, 31),
                workouts=(
                    Workout.create(
                        scheduled_for=date(2027, 1, 3),
                        workout_type="easy_run",
                        purpose="Aerobic base",
                        planned_duration_minutes=45,
                        id="domain-workout-id",
                    ),
                ),
            ),
        )
        recommendation = SqlAlchemyRecommendationRepository(uow.session).create_recommendation(
            user_id=owner.id,
            title="Shorten the workout",
            rationale="Reduce load",
        )
        workout = saved_plan.workouts[0]
        before_payload = workout.to_payload()
        after_payload = {**before_payload, "planned_duration_minutes": 30}
        proposal = repository.create_adjustment_proposal(
            owner.id,
            PlanAdjustmentProposal.create(
                user_id=owner.id,
                training_plan_id=saved_plan.id,
                workout_id=workout.id,
                before_payload=before_payload,
                after_payload=after_payload,
                recommendation_id=recommendation.id,
            ).transition_to("approved"),
        )
        blocked = repository.create_adjustment_proposal(
            other.id,
            PlanAdjustmentProposal.create(
                user_id=other.id,
                training_plan_id=saved_plan.id,
                workout_id=workout.id,
                before_payload=before_payload,
                after_payload=after_payload,
            ),
        )
        uow.commit()

    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        repository = SqlAlchemyTrainingPlanRepository(uow.session)
        proposals = repository.list_adjustment_proposals_for_plan(owner.id, saved_plan.id)
        hidden = repository.list_adjustment_proposals_for_plan(other.id, saved_plan.id)
        loaded_plan = repository.get_plan_for_user(owner.id, saved_plan.id)

        assert proposal is not None
        assert blocked is None
        assert len(proposals) == 1
        assert hidden == []
        assert proposals[0].id == proposal.id
        assert proposals[0].status == "approved"
        assert proposals[0].workout_id == workout.id
        assert proposals[0].recommendation_id == recommendation.id
        assert proposals[0].before_payload["planned_duration_minutes"] == 45
        assert proposals[0].after_payload["planned_duration_minutes"] == 30
        assert loaded_plan is not None
        assert loaded_plan.workouts[0].planned_duration_minutes == 45


def test_repositories_update_recommendation_decision(sqlite_session_factory) -> None:
    Base.metadata.create_all(sqlite_session_factory.kw["bind"])

    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        user = SqlAlchemyUserRepository(uow.session).create_user(
            email="decision@example.com",
            display_name="Decision Runner",
        )
        recommendations = SqlAlchemyRecommendationRepository(uow.session)
        recommendation = recommendations.create_recommendation(
            user_id=user.id,
            title="Reduce tomorrow's workout",
            rationale="High fatigue trend",
            evidence={"fatigue_score": 82},
        )
        recommendations.record_decision(recommendation.id, decision="accepted")
        uow.commit()

    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        loaded = SqlAlchemyRecommendationRepository(uow.session).get(recommendation.id)

        assert loaded is not None
        assert loaded.decision == "accepted"
        assert loaded.decision_at is not None


def test_duplicate_provider_activity_is_rejected(sqlite_session_factory) -> None:
    Base.metadata.create_all(sqlite_session_factory.kw["bind"])

    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        user = UserModel(email="activity@example.com", display_name="Activity Runner")
        uow.session.add(user)
        uow.session.flush()
        connection = SqlAlchemyActivityRepository(uow.session).create_connection(
            user_id=user.id,
            provider="strava",
            provider_account_id="acct-1",
        )
        activity = ActivityModel(
            user_id=user.id,
            provider_connection_id=connection.id,
            provider_activity_id="provider-activity-1",
            started_at=datetime(2027, 1, 1, tzinfo=timezone.utc),
            activity_type="run",
        )
        duplicate = ActivityModel(
            user_id=user.id,
            provider_connection_id=connection.id,
            provider_activity_id="provider-activity-1",
            started_at=datetime(2027, 1, 2, tzinfo=timezone.utc),
            activity_type="run",
        )
        uow.session.add_all([activity, duplicate])

        with pytest.raises(IntegrityError):
            uow.session.flush()


def test_activity_repository_round_trips_manual_and_provider_activities(sqlite_session_factory) -> None:
    Base.metadata.create_all(sqlite_session_factory.kw["bind"])

    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        owner = UserModel(email="activity-owner@example.com", display_name="Activity Owner")
        other = UserModel(email="activity-other@example.com", display_name="Activity Other")
        uow.session.add_all([owner, other])
        uow.session.flush()
        repository = SqlAlchemyActivityRepository(uow.session)
        connection = repository.create_connection(
            user_id=owner.id,
            provider="garmin_connect",
            provider_account_id="garmin-account-1",
        )
        manual = repository.save_activity(
            owner.id,
            CompletedActivity.create(
                user_id=owner.id,
                source="manual",
                started_at=datetime(2027, 1, 3, 7, 30, tzinfo=timezone.utc),
                sport_type="run",
                distance_meters=10_000,
                duration_seconds=3_600,
                average_heart_rate=145,
                elevation_gain_meters=120,
            ),
        )
        provider = repository.save_activity(
            owner.id,
            CompletedActivity.create(
                user_id=owner.id,
                source="garmin_connect",
                source_activity_id="garmin-activity-1",
                provider_connection_id=connection.id,
                started_at=datetime(2027, 1, 4, 7, 30, tzinfo=timezone.utc),
                sport_type="run",
                distance_meters=5_000,
                duration_seconds=1_500,
                average_pace_seconds_per_km=295,
            ),
        )
        uow.commit()

    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        repository = SqlAlchemyActivityRepository(uow.session)
        loaded_manual = repository.get_activity_for_user(owner.id, manual.id)
        loaded_provider = repository.get_activity_for_user(owner.id, provider.id)
        hidden = repository.get_activity_for_user(other.id, manual.id)
        activities = repository.list_activities_for_user(owner.id)

        assert loaded_manual is not None
        assert loaded_manual.source == "manual"
        assert loaded_manual.average_pace_seconds_per_km == pytest.approx(360)
        assert loaded_manual.average_heart_rate == 145
        assert loaded_manual.elevation_gain_meters == 120
        assert loaded_provider is not None
        assert loaded_provider.source == "garmin_connect"
        assert loaded_provider.source_activity_id == "garmin-activity-1"
        assert loaded_provider.provider_connection_id == connection.id
        assert loaded_provider.average_pace_seconds_per_km == 295
        assert hidden is None
        assert [activity.id for activity in activities] == [manual.id, provider.id]


def test_activity_repository_rejects_duplicate_provider_and_allows_manual_duplicates(sqlite_session_factory) -> None:
    Base.metadata.create_all(sqlite_session_factory.kw["bind"])

    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        user = UserModel(email="activity-dupe@example.com", display_name="Activity Dupe")
        uow.session.add(user)
        uow.session.flush()
        repository = SqlAlchemyActivityRepository(uow.session)
        connection = repository.create_connection(
            user_id=user.id,
            provider="garmin_connect",
            provider_account_id="garmin-account-1",
        )
        provider_activity = CompletedActivity.create(
            user_id=user.id,
            source="garmin_connect",
            source_activity_id="garmin-activity-1",
            provider_connection_id=connection.id,
            started_at=datetime(2027, 1, 3, 7, 30, tzinfo=timezone.utc),
            sport_type="run",
            distance_meters=10_000,
            duration_seconds=3_600,
        )
        repository.save_activity(user.id, provider_activity)
        with pytest.raises(IntegrityError):
            repository.save_activity(user.id, provider_activity)

    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        user = UserModel(email="activity-manual-dupe@example.com", display_name="Manual Dupe")
        uow.session.add(user)
        uow.session.flush()
        repository = SqlAlchemyActivityRepository(uow.session)
        manual = CompletedActivity.create(
            user_id=user.id,
            source="manual",
            started_at=datetime(2027, 1, 3, 7, 30, tzinfo=timezone.utc),
            sport_type="run",
            distance_meters=10_000,
            duration_seconds=3_600,
        )
        first = repository.save_activity(user.id, manual)
        second = repository.save_activity(user.id, manual)
        uow.commit()

    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        activities = SqlAlchemyActivityRepository(uow.session).list_activities_for_user(user.id)

        assert len(activities) == 2
        assert first.id != second.id


def test_activity_repository_round_trips_daily_health_metrics(sqlite_session_factory) -> None:
    Base.metadata.create_all(sqlite_session_factory.kw["bind"])

    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        owner = UserModel(email="health-owner@example.com", display_name="Health Owner")
        other = UserModel(email="health-other@example.com", display_name="Health Other")
        uow.session.add_all([owner, other])
        uow.session.flush()
        repository = SqlAlchemyActivityRepository(uow.session)
        repository.save_daily_health_metrics(
            owner.id,
            DailyHealthMetrics.create(
                user_id=owner.id,
                metric_date=date(2027, 1, 3),
                source="manual",
                sleep_duration_minutes=480,
                sleep_quality=82,
                hrv_ms=55,
                hrv_baseline_ms=50,
                resting_heart_rate=48,
                stress_score=22,
            ),
        )
        repository.save_daily_health_metrics(
            owner.id,
            DailyHealthMetrics.create(
                user_id=owner.id,
                metric_date=date(2027, 1, 4),
                source="manual",
                resting_heart_rate=49,
            ),
        )
        uow.commit()

    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        repository = SqlAlchemyActivityRepository(uow.session)
        full = repository.get_daily_health_metrics_for_user(owner.id, date(2027, 1, 3))
        sparse = repository.get_daily_health_metrics_for_user(owner.id, date(2027, 1, 4))
        hidden = repository.get_daily_health_metrics_for_user(other.id, date(2027, 1, 3))

        assert full is not None
        assert full.source == "manual"
        assert full.values_by_metric_type()["sleep_duration_minutes"] == 480
        assert full.values_by_metric_type()["stress_score"] == 22
        assert sparse is not None
        assert sparse.values_by_metric_type() == {"resting_heart_rate": 49}
        assert hidden is None


def test_activity_repository_persists_workout_match(sqlite_session_factory) -> None:
    Base.metadata.create_all(sqlite_session_factory.kw["bind"])

    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        user = UserModel(email="activity-match@example.com", display_name="Activity Match")
        uow.session.add(user)
        uow.session.flush()
        training_plans = SqlAlchemyTrainingPlanRepository(uow.session)
        plan = training_plans.save_plan(
            user.id,
            TrainingPlan.create(
                user_id=user.id,
                name="Match Plan",
                starts_on=date(2027, 1, 1),
                ends_on=date(2027, 1, 31),
                workouts=(
                    Workout.create(
                        scheduled_for=date(2027, 1, 3),
                        workout_type="easy_run",
                        purpose="Aerobic base",
                        planned_duration_minutes=45,
                    ),
                ),
            ),
        )
        activity = CompletedActivity.create(
            user_id=user.id,
            source="manual",
            started_at=datetime(2027, 1, 3, 7, 30, tzinfo=timezone.utc),
            sport_type="run",
            distance_meters=8_000,
            duration_seconds=2_880,
        )
        matched = match_activity_to_workout(activity, plan.workouts)
        saved = SqlAlchemyActivityRepository(uow.session).save_activity(user.id, matched)
        uow.commit()

    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        loaded = SqlAlchemyActivityRepository(uow.session).get_activity_for_user(user.id, saved.id)

        assert loaded is not None
        assert loaded.matched_workout_id == plan.workouts[0].id


def test_orphan_workout_is_rejected(sqlite_session_factory) -> None:
    Base.metadata.create_all(sqlite_session_factory.kw["bind"])

    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        with pytest.raises(IntegrityError):
            SqlAlchemyTrainingPlanRepository(uow.session).add_workout(
                training_plan_id="missing-plan",
                scheduled_for=date(2027, 1, 2),
                workout_type="easy_run",
                planned_duration_minutes=45,
            )
            uow.session.flush()


def test_athlete_profile_can_be_linked_to_user(sqlite_session_factory) -> None:
    Base.metadata.create_all(sqlite_session_factory.kw["bind"])

    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        user = UserModel(email="profile@example.com", display_name="Profile Runner")
        uow.session.add(user)
        uow.session.flush()
        profile = AthleteProfileModel(
            user_id=user.id,
            timezone="Asia/Taipei",
            experience_level="intermediate",
        )
        uow.session.add(profile)
        uow.commit()

    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        loaded = uow.session.get(UserModel, user.id)

        assert loaded is not None
        assert loaded.athlete_profile.timezone == "Asia/Taipei"


def test_athlete_profile_repository_round_trips_profile_and_preferences(sqlite_session_factory) -> None:
    Base.metadata.create_all(sqlite_session_factory.kw["bind"])

    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        user = UserModel(email="athlete-domain@example.com", display_name="Athlete Domain Runner")
        uow.session.add(user)
        uow.session.flush()
        repository = SqlAlchemyAthleteRaceRepository(uow.session)
        saved = repository.save_profile(
            user.id,
            AthleteProfile.create(
                user_id=user.id,
                timezone="Asia/Taipei",
                experience_level="intermediate",
                current_weekly_mileage_km=42.5,
                preferred_training_days=("tuesday", "thursday", "sunday"),
                preferred_long_run_day="sunday",
                max_runs_per_week=4,
            )
        )
        updated = repository.save_profile(
            user.id,
            saved.with_preferences(
                AthletePreferences(
                    preferred_training_days=("monday", "wednesday", "saturday"),
                    preferred_long_run_day="saturday",
                    max_runs_per_week=3,
                    unit_preference="imperial",
                    training_preferences={"surface": "trail"},
                    injury_notes="Avoid aggressive downhill sessions.",
                )
            )
        )
        uow.commit()

    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        loaded = SqlAlchemyAthleteRaceRepository(uow.session).get_profile_for_user(user.id)

        assert loaded is not None
        assert loaded.id == updated.id
        assert loaded.user_id == user.id
        assert loaded.timezone == "Asia/Taipei"
        assert loaded.experience_level == "intermediate"
        assert loaded.current_weekly_mileage_km == 42.5
        assert loaded.preferences.preferred_training_days == ("monday", "wednesday", "saturday")
        assert loaded.preferences.preferred_long_run_day == "saturday"
        assert loaded.preferences.max_runs_per_week == 3
        assert loaded.preferences.unit_preference == "imperial"
        assert loaded.preferences.training_preferences == {"surface": "trail"}
        assert loaded.preferences.injury_notes == "Avoid aggressive downhill sessions."


def test_race_goal_repository_round_trips_goals_and_enforces_user_ownership(sqlite_session_factory) -> None:
    Base.metadata.create_all(sqlite_session_factory.kw["bind"])

    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        owner = UserModel(email="race-owner@example.com", display_name="Race Owner")
        other = UserModel(email="race-other@example.com", display_name="Race Other")
        uow.session.add_all([owner, other])
        uow.session.flush()
        repository = SqlAlchemyAthleteRaceRepository(uow.session)
        saved = repository.create_race_goal(
            owner.id,
            RaceGoal.create(
                user_id=owner.id,
                name="Taipei Half Marathon",
                race_date=date(2027, 3, 1),
                distance_meters=21_097,
                target_finish_seconds=7_200,
                priority="primary",
            )
        )
        repository.create_race_goal(
            other.id,
            RaceGoal.create(
                user_id=other.id,
                name="Other Runner 10K",
                race_date=date(2027, 4, 1),
                distance_meters=10_000,
            )
        )
        uow.commit()

    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        repository = SqlAlchemyAthleteRaceRepository(uow.session)
        loaded = repository.get_race_goal_for_user(owner.id, saved.id)
        hidden = repository.get_race_goal_for_user(other.id, saved.id)
        owner_goals = repository.list_race_goals_for_user(owner.id)

        assert loaded is not None
        assert loaded.name == "Taipei Half Marathon"
        assert loaded.race_date == date(2027, 3, 1)
        assert loaded.distance_meters == 21_097
        assert loaded.target_finish_seconds == 7_200
        assert loaded.priority == "primary"
        assert loaded.status == "planned"
        assert loaded.target_pace_seconds_per_km == pytest.approx(341.28, abs=0.01)
        assert hidden is None
        assert [goal.id for goal in owner_goals] == [saved.id]


def test_race_goal_repository_updates_only_user_owned_goals(sqlite_session_factory) -> None:
    Base.metadata.create_all(sqlite_session_factory.kw["bind"])

    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        owner = UserModel(email="race-update-owner@example.com", display_name="Race Owner")
        other = UserModel(email="race-update-other@example.com", display_name="Race Other")
        uow.session.add_all([owner, other])
        uow.session.flush()
        repository = SqlAlchemyAthleteRaceRepository(uow.session)
        saved = repository.create_race_goal(
            owner.id,
            RaceGoal.create(
                user_id=owner.id,
                name="Original 10K",
                race_date=date(2027, 5, 1),
                distance_meters=10_000,
            )
        )
        uow.commit()

    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        repository = SqlAlchemyAthleteRaceRepository(uow.session)
        blocked = repository.update_race_goal(
            other.id,
            RaceGoal.create(
                id=saved.id,
                user_id=other.id,
                name="Blocked Update",
                race_date=date(2027, 5, 2),
                distance_meters=5_000,
            )
        )
        allowed = repository.update_race_goal(
            owner.id,
            RaceGoal.create(
                id=saved.id,
                user_id=owner.id,
                name="Updated 10K",
                race_date=date(2027, 5, 2),
                distance_meters=10_000,
                target_finish_seconds=3_600,
                priority="secondary",
                status="active",
            )
        )
        uow.commit()

    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        loaded = SqlAlchemyAthleteRaceRepository(uow.session).get_race_goal_for_user(owner.id, saved.id)

        assert blocked is None
        assert allowed is not None
        assert loaded is not None
        assert loaded.name == "Updated 10K"
        assert loaded.race_date == date(2027, 5, 2)
        assert loaded.target_finish_seconds == 3_600
        assert loaded.priority == "secondary"
        assert loaded.status == "active"


def test_athlete_profile_repository_rejects_mismatched_tenant_payload(sqlite_session_factory) -> None:
    Base.metadata.create_all(sqlite_session_factory.kw["bind"])

    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        user = UserModel(email="tenant-profile@example.com", display_name="Tenant Profile")
        other = UserModel(email="tenant-profile-other@example.com", display_name="Other Tenant")
        uow.session.add_all([user, other])
        uow.session.flush()
        repository = SqlAlchemyAthleteRaceRepository(uow.session)

        with pytest.raises(ValueError, match="user_id"):
            repository.save_profile(
                user.id,
                AthleteProfile.create(
                    user_id=other.id,
                    timezone="Asia/Taipei",
                    experience_level="beginner",
                    current_weekly_mileage_km=10,
                    preferred_training_days=("sunday",),
                    preferred_long_run_day="sunday",
                    max_runs_per_week=1,
                ),
            )


def test_race_goal_repository_rejects_mismatched_tenant_payload(sqlite_session_factory) -> None:
    Base.metadata.create_all(sqlite_session_factory.kw["bind"])

    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        user = UserModel(email="tenant-race@example.com", display_name="Tenant Race")
        other = UserModel(email="tenant-race-other@example.com", display_name="Other Tenant")
        uow.session.add_all([user, other])
        uow.session.flush()
        repository = SqlAlchemyAthleteRaceRepository(uow.session)

        with pytest.raises(ValueError, match="user_id"):
            repository.create_race_goal(
                user.id,
                RaceGoal.create(
                    user_id=other.id,
                    name="Mismatched Create",
                    race_date=date(2027, 5, 1),
                    distance_meters=10_000,
                ),
            )

        with pytest.raises(ValueError, match="user_id"):
            repository.update_race_goal(
                user.id,
                RaceGoal.create(
                    id="race-1",
                    user_id=other.id,
                    name="Mismatched Race",
                    race_date=date(2027, 5, 1),
                    distance_meters=10_000,
                ),
            )


def test_race_goal_repository_lists_with_date_range_and_paging(sqlite_session_factory) -> None:
    Base.metadata.create_all(sqlite_session_factory.kw["bind"])

    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        user = UserModel(email="race-list@example.com", display_name="Race List")
        uow.session.add(user)
        uow.session.flush()
        repository = SqlAlchemyAthleteRaceRepository(uow.session)
        for name, race_date in (
            ("January 10K", date(2027, 1, 15)),
            ("March Half", date(2027, 3, 1)),
            ("May 10K", date(2027, 5, 1)),
            ("June Marathon", date(2027, 6, 15)),
        ):
            repository.create_race_goal(
                user.id,
                RaceGoal.create(
                    user_id=user.id,
                    name=name,
                    race_date=race_date,
                    distance_meters=10_000,
                )
            )
        uow.commit()

    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        repository = SqlAlchemyAthleteRaceRepository(uow.session)
        goals = repository.list_race_goals_for_user(
            user.id,
            race_date_from=date(2027, 2, 1),
            race_date_to=date(2027, 6, 1),
            limit=1,
            offset=1,
        )

        assert [goal.name for goal in goals] == ["May 10K"]


def test_google_identity_can_be_linked_without_auth_broker_coupling(sqlite_session_factory) -> None:
    Base.metadata.create_all(sqlite_session_factory.kw["bind"])

    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        user = UserModel(email="sso@example.com", display_name="SSO Runner")
        uow.session.add(user)
        uow.session.flush()
        identity = AuthIdentityModel(
            user_id=user.id,
            provider="google",
            issuer="https://accounts.google.com",
            subject="google-user-123",
            email="sso@example.com",
            provider_claims={"email_verified": True, "broker": None},
        )
        uow.session.add(identity)
        uow.commit()

    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        loaded = uow.session.get(AuthIdentityModel, identity.id)

        assert loaded is not None
        assert loaded.user_id == user.id
        assert loaded.provider == "google"
        assert loaded.provider_claims["broker"] is None


def test_duplicate_sso_subject_for_provider_is_rejected(sqlite_session_factory) -> None:
    Base.metadata.create_all(sqlite_session_factory.kw["bind"])

    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        user = UserModel(email="dupe-sso@example.com", display_name="SSO Runner")
        uow.session.add(user)
        uow.session.flush()
        uow.session.add_all(
            [
                AuthIdentityModel(
                    user_id=user.id,
                    provider="github",
                    issuer="https://github.com/login/oauth",
                    subject="github-user-123",
                    email="dupe-sso@example.com",
                ),
                AuthIdentityModel(
                    user_id=user.id,
                    provider="github",
                    issuer="https://github.com/login/oauth",
                    subject="github-user-123",
                    email="dupe-sso@example.com",
                ),
            ]
        )

        with pytest.raises(IntegrityError):
            uow.session.flush()


def test_garminconnect_connection_tracks_tokenstore_credential_lifecycle(sqlite_session_factory) -> None:
    Base.metadata.create_all(sqlite_session_factory.kw["bind"])

    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        user = UserModel(email="garmin@example.com", display_name="Garmin Runner")
        uow.session.add(user)
        uow.session.flush()
        connection = SqlAlchemyActivityRepository(uow.session).create_connection(
            user_id=user.id,
            provider="garmin_connect",
            provider_account_id="garmin-account-1",
            provider_display_name="Garmin Runner",
            auth_scheme="garminconnect_tokenstore",
            credential_format="garminconnect_tokenstore",
            credential_secret_ref="secret://garmin/runner/tokenstore",
            capabilities={"read": ["activities", "sleep", "steps", "heart_rates", "stress", "spo2"]},
            provider_metadata={"region": "global"},
        )
        SqlAlchemyActivityRepository(uow.session).record_credential_refresh(connection.id)
        uow.commit()

    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        loaded = uow.session.get(type(connection), connection.id)

        assert loaded is not None
        assert loaded.provider == "garmin_connect"
        assert loaded.provider_display_name == "Garmin Runner"
        assert loaded.auth_scheme == "garminconnect_tokenstore"
        assert loaded.credential_format == "garminconnect_tokenstore"
        assert loaded.credential_status == "active"
        assert loaded.credential_secret_ref == "secret://garmin/runner/tokenstore"
        assert loaded.capabilities["read"] == ["activities", "sleep", "steps", "heart_rates", "stress", "spo2"]
        assert loaded.provider_metadata == {"region": "global"}
        assert loaded.last_credential_refresh_at is not None
        assert loaded.credential_rotated_at is not None


def test_garmin_health_metric_keeps_provider_summary_without_credentials(sqlite_session_factory) -> None:
    Base.metadata.create_all(sqlite_session_factory.kw["bind"])

    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        user = UserModel(email="garmin-health@example.com", display_name="Garmin Health Runner")
        uow.session.add(user)
        uow.session.flush()
        connection = SqlAlchemyActivityRepository(uow.session).create_connection(
            user_id=user.id,
            provider="garmin_connect",
            provider_account_id="garmin-account-1",
            auth_scheme="garminconnect_tokenstore",
            credential_format="garminconnect_tokenstore",
            credential_secret_ref="secret://garmin/runner/tokenstore",
        )
        metric = HealthMetricModel(
            user_id=user.id,
            provider_connection_id=connection.id,
            provider_metric_id="garmin-resting-heart-rate-2027-01-01",
            measured_at=datetime(2027, 1, 1, tzinfo=timezone.utc),
            metric_type="resting_heart_rate",
            value=47,
            unit="bpm",
            provider_summary={"source_method": "get_rhr_day", "calendarDate": "2027-01-01"},
        )
        uow.session.add(metric)
        uow.commit()

    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        loaded = uow.session.get(HealthMetricModel, metric.id)

        assert loaded is not None
        assert loaded.provider_connection_id == connection.id
        assert loaded.provider_summary["source_method"] == "get_rhr_day"
        assert "password" not in loaded.provider_summary
        assert "session_data" not in loaded.provider_summary


def test_agent_observability_records_steps_and_context_sources(sqlite_session_factory) -> None:
    Base.metadata.create_all(sqlite_session_factory.kw["bind"])

    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        user = UserModel(email="agent-observe@example.com", display_name="Observed Runner")
        uow.session.add(user)
        uow.session.flush()
        agent_run = AgentRunModel(
            user_id=user.id,
            status="completed",
            provider="openai",
            model="gpt-5",
            trigger_type="scheduled",
            workflow_name="daily_recommendation",
            prompt_version="daily-v1",
            correlation_id="corr-123",
            latency_ms=1520,
            input_tokens=1200,
            output_tokens=320,
            total_tokens=1520,
            estimated_cost_cents=4,
            input_summary="Daily context for runner",
            output_summary="Recommended reducing workout intensity",
            metadata_json={"environment": "test"},
        )
        uow.session.add(agent_run)
        uow.session.flush()
        uow.session.add_all(
            [
                AgentRunStepModel(
                    agent_run_id=agent_run.id,
                    sequence_number=1,
                    step_type="context_build",
                    name="Build daily context",
                    status="completed",
                    latency_ms=100,
                    output_summary="Loaded plan and recovery context",
                    payload={"context_items": 3},
                ),
                AgentRunStepModel(
                    agent_run_id=agent_run.id,
                    sequence_number=2,
                    step_type="tool_call",
                    name="Load recovery",
                    tool_name="recovery_context",
                    status="completed",
                    latency_ms=240,
                    input_summary="Need recovery context",
                    output_summary="Recovery score high fatigue",
                    payload={"fatigue_score": 82},
                ),
                AgentContextSourceModel(
                    agent_run_id=agent_run.id,
                    source_type="health_metric",
                    source_id="metric-1",
                    source_summary="Resting heart rate elevated",
                    relevance_score=0.91,
                    metadata_json={"metric_type": "resting_heart_rate"},
                ),
            ]
        )
        uow.commit()

    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        loaded_run = uow.session.get(AgentRunModel, agent_run.id)
        steps = uow.session.query(AgentRunStepModel).filter_by(agent_run_id=agent_run.id).order_by(
            AgentRunStepModel.sequence_number
        )
        sources = uow.session.query(AgentContextSourceModel).filter_by(agent_run_id=agent_run.id).all()

        assert loaded_run is not None
        assert loaded_run.workflow_name == "daily_recommendation"
        assert loaded_run.total_tokens == 1520
        assert [step.step_type for step in steps] == ["context_build", "tool_call"]
        assert sources[0].source_type == "health_metric"
        assert sources[0].metadata_json == {"metric_type": "resting_heart_rate"}


def test_integration_resource_cursors_track_independent_sync_progress(sqlite_session_factory) -> None:
    Base.metadata.create_all(sqlite_session_factory.kw["bind"])

    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        user = UserModel(email="cursor@example.com", display_name="Cursor Runner")
        uow.session.add(user)
        uow.session.flush()
        repository = SqlAlchemyActivityRepository(uow.session)
        connection = repository.create_connection(
            user_id=user.id,
            provider="garmin_connect",
            provider_account_id="garmin-account-1",
            auth_scheme="garminconnect_tokenstore",
            credential_format="garminconnect_tokenstore",
            credential_secret_ref="secret://garmin/runner/tokenstore",
        )
        activities_cursor = repository.upsert_resource_cursor(
            integration_connection_id=connection.id,
            resource_type="activities",
            cursor_value={"last_activity_id": "12345"},
            sync_until=datetime(2027, 1, 3, tzinfo=timezone.utc),
            status="ready",
        )
        sleep_cursor = repository.upsert_resource_cursor(
            integration_connection_id=connection.id,
            resource_type="sleep",
            cursor_value={"date": "2027-01-01"},
            sync_until=datetime(2027, 1, 1, tzinfo=timezone.utc),
            status="error",
            metadata_json={"last_error": "provider temporarily unavailable"},
        )
        uow.commit()

    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        cursors = {
            cursor.resource_type: cursor
            for cursor in uow.session.query(IntegrationResourceCursorModel)
            .filter_by(integration_connection_id=connection.id)
            .all()
        }

        assert set(cursors) == {"activities", "sleep"}
        assert cursors["activities"].id == activities_cursor.id
        assert cursors["activities"].cursor_value == {"last_activity_id": "12345"}
        assert cursors["activities"].status == "ready"
        assert cursors["sleep"].id == sleep_cursor.id
        assert cursors["sleep"].cursor_value == {"date": "2027-01-01"}
        assert cursors["sleep"].status == "error"
        assert cursors["sleep"].metadata_json["last_error"] == "provider temporarily unavailable"
