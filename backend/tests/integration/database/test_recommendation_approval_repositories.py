from datetime import date

from src.domain.recommendation_approval import EvidenceItem, ProposedAction, Recommendation
from src.domain.training_plan import PlanAdjustmentProposal, TrainingPlan, Workout
from src.infrastructure.database.models import Base, RecommendationModel, UserModel
from src.infrastructure.database.recommendation_repository import SqlAlchemyRecommendationRepository
from src.infrastructure.database.training_plan_repository import SqlAlchemyTrainingPlanRepository
from src.infrastructure.database.uow import SqlAlchemyUnitOfWork


def _workout() -> Workout:
    return Workout.create(
        id="workout-1",
        scheduled_for=date(2027, 1, 28),
        workout_type="easy_run",
        purpose="Aerobic base",
        planned_duration_minutes=45,
        planned_distance_meters=8_000,
    )


def _recommendation(
    *,
    user_id: str,
    training_plan_id: str = "plan-1",
    duration: int = 30,
    title: str = "Reduce today's run",
) -> Recommendation:
    before = _workout().to_payload()
    after = {**before, "planned_duration_minutes": duration}
    return Recommendation.create(
        user_id=user_id,
        recommendation_type="workout_adjustment",
        priority="high",
        title=title,
        rationale="Recovery context indicates rest.",
        evidence=(
            EvidenceItem.create(
                source="training_analytics",
                metric="readiness_label",
                value="rest",
                observed_at="2027-01-28",
            ),
        ),
        proposed_action=ProposedAction.adjust_workout(
            training_plan_id=training_plan_id,
            workout_id="workout-1",
            before_payload=before,
            after_payload=after,
            reason="Recovery is low",
        ),
        training_plan_id=training_plan_id,
        workout_id="workout-1",
    )


def test_recommendation_repository_round_trips_domain_payload_and_history_paging(sqlite_session_factory) -> None:
    Base.metadata.create_all(sqlite_session_factory.kw["bind"])

    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        owner = UserModel(email="recommendation-owner@example.com", display_name="Recommendation Owner")
        other = UserModel(email="recommendation-other@example.com", display_name="Recommendation Other")
        uow.session.add_all([owner, other])
        uow.session.flush()
        saved_plan = SqlAlchemyTrainingPlanRepository(uow.session).save_plan(
            owner.id,
            TrainingPlan.create(
                id="plan-1",
                user_id=owner.id,
                name="Build Plan",
                starts_on=date(2027, 1, 1),
                ends_on=date(2027, 2, 28),
                workouts=(_workout(),),
            ),
        )
        repository = SqlAlchemyRecommendationRepository(uow.session)
        first = repository.create_recommendation(
            owner.id,
            _recommendation(user_id=owner.id, training_plan_id=saved_plan.id, title="First"),
        )
        second = repository.create_recommendation(
            owner.id,
            _recommendation(user_id=owner.id, training_plan_id=saved_plan.id, title="Second").reject(),
        )
        third = repository.create_recommendation(
            owner.id,
            _recommendation(user_id=owner.id, training_plan_id=saved_plan.id, title="Third").accept(),
        )
        repository.create_recommendation(
            other.id,
            _recommendation(user_id=other.id, training_plan_id=saved_plan.id, title="Other"),
        )
        uow.commit()

    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        repository = SqlAlchemyRecommendationRepository(uow.session)
        loaded = repository.get_recommendation_for_user(owner.id, first.id)
        hidden = repository.get_recommendation_for_user(other.id, first.id)
        page = repository.list_recommendations_for_user(owner.id, limit=2, offset=1)

        assert loaded is not None
        assert loaded.title == "First"
        assert loaded.evidence[0].metric == "readiness_label"
        assert loaded.proposed_action.payload["after_payload"]["planned_duration_minutes"] == 30
        assert hidden is None
        assert [recommendation.id for recommendation in page] == [second.id, first.id]
        assert repository.get_recommendation_for_user(owner.id, third.id).decision == "accepted"


def test_recommendation_repository_saves_decisions_and_preserves_edited_action_history(sqlite_session_factory) -> None:
    Base.metadata.create_all(sqlite_session_factory.kw["bind"])

    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        user = UserModel(email="recommendation-edit@example.com", display_name="Recommendation Edit")
        uow.session.add(user)
        uow.session.flush()
        saved_plan = SqlAlchemyTrainingPlanRepository(uow.session).save_plan(
            user.id,
            TrainingPlan.create(
                id="plan-1",
                user_id=user.id,
                name="Build Plan",
                starts_on=date(2027, 1, 1),
                ends_on=date(2027, 2, 28),
                workouts=(_workout(),),
            ),
        )
        repository = SqlAlchemyRecommendationRepository(uow.session)
        saved = repository.create_recommendation(
            user.id,
            _recommendation(user_id=user.id, training_plan_id=saved_plan.id, duration=30),
        )
        edited, revised = saved.edit(
            _recommendation(user_id=user.id, training_plan_id=saved_plan.id, duration=20).proposed_action
        )
        repository.save_recommendation(user.id, edited)
        revised = repository.create_recommendation(user.id, revised)
        uow.commit()

    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        repository = SqlAlchemyRecommendationRepository(uow.session)
        original = repository.get_recommendation_for_user(user.id, saved.id)
        revised_loaded = repository.get_recommendation_for_user(user.id, revised.id)

        assert original is not None
        assert original.decision == "edited"
        assert original.proposed_action.payload["after_payload"]["planned_duration_minutes"] == 30
        assert revised_loaded is not None
        assert revised_loaded.status == "pending"
        assert revised_loaded.proposed_action.payload["after_payload"]["planned_duration_minutes"] == 20
        assert revised_loaded.proposed_action.payload["supersedes_recommendation_id"] == saved.id


def test_recommendation_repository_loads_legacy_action_type_payload(sqlite_session_factory) -> None:
    Base.metadata.create_all(sqlite_session_factory.kw["bind"])

    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        user = UserModel(email="legacy-action@example.com", display_name="Legacy Action")
        uow.session.add(user)
        uow.session.flush()
        uow.session.add(
            RecommendationModel(
                user_id=user.id,
                title="Legacy recommendation",
                rationale="Stored before action payloads used type.",
                evidence={
                    "items": [{"source": "legacy", "metric": "readiness_label", "value": "ready"}],
                    "recommendation": {"type": "informational", "priority": "medium"},
                    "proposed_action": {"action_type": "no_plan_change", "reason": "Informational only"},
                },
            )
        )
        uow.commit()

    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        loaded = SqlAlchemyRecommendationRepository(uow.session).list_recommendations_for_user(user.id)

        assert len(loaded) == 1
        assert loaded[0].title == "Legacy recommendation"
        assert loaded[0].proposed_action.action_type == "no_plan_change"
        assert loaded[0].proposed_action.to_payload()["type"] == "no_plan_change"


def test_recommendation_repository_downgrades_historical_training_plan_creation_action(sqlite_session_factory) -> None:
    Base.metadata.create_all(sqlite_session_factory.kw["bind"])

    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        user = UserModel(email="legacy-plan-action@example.com", display_name="Legacy Plan Action")
        uow.session.add(user)
        uow.session.flush()
        uow.session.add(
            RecommendationModel(
                user_id=user.id,
                title="Review generated plan",
                rationale="Stored before direct active training-plan generation.",
                evidence={
                    "items": [{"source": "legacy_agent", "metric": "workflow", "value": "training_plan_generation"}],
                    "recommendation": {"type": "training_plan_creation", "priority": "medium"},
                    "proposed_action": {
                        "type": "create_training_plan",
                        "draft_training_plan_id": "draft-plan-1",
                        "reason": "Approve generated plan.",
                    },
                },
            )
        )
        uow.commit()

    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        loaded = SqlAlchemyRecommendationRepository(uow.session).list_recommendations_for_user(user.id)

        assert len(loaded) == 1
        assert loaded[0].recommendation_type == "informational"
        assert loaded[0].proposed_action.action_type == "no_plan_change"
        assert loaded[0].proposed_action.payload["legacy_action"]["type"] == "create_training_plan"


def test_plan_adjustment_repository_preserves_applied_status_and_payload_history(sqlite_session_factory) -> None:
    Base.metadata.create_all(sqlite_session_factory.kw["bind"])

    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        user = UserModel(email="adjustment-applied@example.com", display_name="Adjustment Applied")
        uow.session.add(user)
        uow.session.flush()
        plans = SqlAlchemyTrainingPlanRepository(uow.session)
        saved_plan = plans.save_plan(
            user.id,
            TrainingPlan.create(
                id="plan-1",
                user_id=user.id,
                name="Build Plan",
                starts_on=date(2027, 1, 1),
                ends_on=date(2027, 2, 28),
                workouts=(_workout(),),
            ),
        )
        before = saved_plan.workouts[0].to_payload()
        after = {**before, "planned_duration_minutes": 30}
        adjustment = plans.create_adjustment_proposal(
            user.id,
            PlanAdjustmentProposal.create(
                user_id=user.id,
                training_plan_id=saved_plan.id,
                workout_id=saved_plan.workouts[0].id,
                before_payload=before,
                after_payload=after,
                status="applied",
            ),
        )
        uow.commit()

    with SqlAlchemyUnitOfWork(sqlite_session_factory) as uow:
        proposals = SqlAlchemyTrainingPlanRepository(uow.session).list_adjustment_proposals_for_plan(
            user.id,
            saved_plan.id,
        )

        assert adjustment is not None
        assert proposals[0].status == "applied"
        assert proposals[0].before_payload["planned_duration_minutes"] == 45
        assert proposals[0].after_payload["planned_duration_minutes"] == 30
