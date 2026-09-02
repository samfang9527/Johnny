from datetime import date

from src.application.recommendation_approval import (
    AcceptRecommendationHandler,
    CreateDailyRecommendationHandler,
    EditRecommendationHandler,
    RejectRecommendationHandler,
)
from src.domain.recommendation_approval import EvidenceItem, ProposedAction, Recommendation
from src.domain.training_analytics import RecoveryContext, TodayContext, TrainingLoadSummary
from src.domain.training_plan import TrainingPlan, Workout


class FakeRecommendationStore:
    def __init__(self) -> None:
        self.recommendations: dict[str, Recommendation] = {}
        self.next_id = 1

    def create_recommendation(self, user_id: str, recommendation: Recommendation) -> Recommendation:
        saved = Recommendation.create(
            id=f"recommendation-{self.next_id}",
            user_id=user_id,
            recommendation_type=recommendation.recommendation_type,
            priority=recommendation.priority,
            title=recommendation.title,
            rationale=recommendation.rationale,
            evidence=recommendation.evidence,
            proposed_action=recommendation.proposed_action,
            status=recommendation.status,
            decision=recommendation.decision,
            training_plan_id=recommendation.training_plan_id,
            workout_id=recommendation.workout_id,
            agent_run_id=recommendation.agent_run_id,
        )
        self.next_id += 1
        self.recommendations[saved.id] = saved
        return saved

    def save_recommendation(self, user_id: str, recommendation: Recommendation) -> Recommendation | None:
        if recommendation.user_id != user_id or recommendation.id not in self.recommendations:
            return None
        self.recommendations[recommendation.id] = recommendation
        return recommendation

    def get_recommendation_for_user(self, user_id: str, recommendation_id: str | None) -> Recommendation | None:
        recommendation = self.recommendations.get(recommendation_id or "")
        if recommendation is None or recommendation.user_id != user_id:
            return None
        return recommendation

    def list_recommendations_for_user(
        self,
        user_id: str,
        *,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[Recommendation]:
        recommendations = [item for item in self.recommendations.values() if item.user_id == user_id]
        recommendations.sort(key=lambda item: item.id or "", reverse=True)
        return recommendations[offset : offset + limit if limit is not None else None]


class FakeTrainingPlanStore:
    def __init__(self, plan: TrainingPlan | None) -> None:
        self.plan = plan
        self.adjustments = []
        self.activated_draft_ids: list[str] = []

    def get_plan_for_user(self, user_id: str, plan_id: str | None) -> TrainingPlan | None:
        if self.plan is None or self.plan.user_id != user_id or self.plan.id != plan_id:
            return None
        return self.plan

    def save_plan(self, user_id: str, plan: TrainingPlan) -> TrainingPlan:
        if plan.user_id != user_id:
            raise ValueError("payload user_id does not match repository user_id")
        self.plan = plan
        return plan

    def create_adjustment_proposal(self, user_id: str, proposal):
        self.adjustments.append(proposal)
        return proposal

    def activate_draft_plan(
        self,
        user_id: str,
        plan_id: str | None,
        *,
        accepted_at: date,
        conflict_created_after=None,
    ) -> TrainingPlan | None:
        if self.plan is None or self.plan.user_id != user_id or self.plan.id != plan_id or self.plan.status != "draft":
            return None
        self.activated_draft_ids.append(plan_id)
        self.plan = TrainingPlan.create(
            id=self.plan.id,
            user_id=self.plan.user_id,
            race_id=self.plan.race_id,
            name=self.plan.name,
            status="active",
            starts_on=self.plan.starts_on,
            ends_on=self.plan.ends_on,
            workouts=self.plan.workouts,
        )
        return self.plan


def _workout(*, duration: int = 45, status: str = "planned") -> Workout:
    return Workout.create(
        id="workout-1",
        scheduled_for=date(2027, 1, 28),
        workout_type="easy_run",
        purpose="Aerobic base",
        planned_duration_minutes=duration,
        planned_distance_meters=8_000,
        status=status,
    )


def _plan(workout: Workout | None = None, *, user_id: str = "user-1") -> TrainingPlan:
    return TrainingPlan.create(
        id="plan-1",
        user_id=user_id,
        name="Build Plan",
        starts_on=date(2027, 1, 1),
        ends_on=date(2027, 2, 28),
        workouts=(workout or _workout(),),
    )


def _recommendation(*, user_id: str = "user-1", duration: int = 30) -> Recommendation:
    before = _workout().to_payload()
    after = {**before, "planned_duration_minutes": duration}
    return Recommendation.create(
        user_id=user_id,
        recommendation_type="workout_adjustment",
        priority="high",
        title="Reduce today's run",
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
            training_plan_id="plan-1",
            workout_id="workout-1",
            before_payload=before,
            after_payload=after,
            reason="Recovery is low",
        ),
    )


def _training_plan_creation_recommendation(*, user_id: str = "user-1") -> Recommendation:
    return Recommendation.create(
        user_id=user_id,
        recommendation_type="training_plan_creation",
        priority="medium",
        title="Review generated plan",
        rationale="A generated draft plan is ready.",
        evidence=(
            EvidenceItem.create(
                source="agent",
                metric="plan_weeks",
                value=4,
                observed_at="2027-01-28",
            ),
        ),
        proposed_action=ProposedAction.create_training_plan(
            draft_training_plan_id="draft-plan-1",
            reason="A structured plan is needed.",
            summary="Four-week race build.",
        ),
    )


def _draft_plan(*, user_id: str = "user-1") -> TrainingPlan:
    return TrainingPlan.create(
        id="draft-plan-1",
        user_id=user_id,
        name="Generated Draft",
        starts_on=date(2027, 1, 1),
        ends_on=date(2027, 1, 28),
        status="draft",
        workouts=(_workout(),),
    )


def _today_context(*, readiness: str = "rest", scheduled_workouts: tuple[dict, ...] | None = None) -> TodayContext:
    return TodayContext(
        user_id="user-1",
        anchor_date=date(2027, 1, 28),
        scheduled_workouts=scheduled_workouts if scheduled_workouts is not None else (_workout().to_payload(),),
        recent_activities=(),
        training_load=TrainingLoadSummary(
            user_id="user-1",
            anchor_date=date(2027, 1, 28),
            weekly_distance_meters=12_000,
            previous_weekly_distance_meters=8_000,
            mileage_ramp_percentage=50,
            acute_load=80,
            chronic_load=50,
            acute_chronic_ratio=1.6,
        ),
        recovery=RecoveryContext(
            user_id="user-1",
            anchor_date=date(2027, 1, 28),
            readiness_label=readiness,
            sleep_debt_minutes=120,
            hrv_delta_percentage=-12,
            resting_heart_rate_baseline=48,
            resting_heart_rate_delta_bpm=5,
            stress_score=70,
            body_battery_score=None,
        ),
    )


def test_pending_recommendation_does_not_mutate_workout_before_acceptance() -> None:
    recommendations = FakeRecommendationStore()
    saved = recommendations.create_recommendation("user-1", _recommendation())
    plans = FakeTrainingPlanStore(_plan())

    loaded_plan = plans.get_plan_for_user("user-1", saved.training_plan_id)

    assert loaded_plan is not None
    assert loaded_plan.workouts[0].planned_duration_minutes == 45
    assert saved.status == "pending"


def test_accepting_recommendation_applies_matching_workout_adjustment() -> None:
    recommendations = FakeRecommendationStore()
    saved = recommendations.create_recommendation("user-1", _recommendation(duration=30))
    plans = FakeTrainingPlanStore(_plan())
    handler = AcceptRecommendationHandler(recommendations=recommendations, training_plans=plans)

    decided = handler.handle(user_id="user-1", recommendation_id=saved.id)

    assert decided is not None
    assert decided.status == "decided"
    assert decided.decision == "accepted"
    assert plans.plan is not None
    assert plans.plan.workouts[0].planned_duration_minutes == 30
    assert plans.adjustments[0].status == "applied"


def test_accepting_training_plan_creation_activates_draft_after_user_decision() -> None:
    recommendations = FakeRecommendationStore()
    saved = recommendations.create_recommendation("user-1", _training_plan_creation_recommendation())
    plans = FakeTrainingPlanStore(_draft_plan())
    handler = AcceptRecommendationHandler(recommendations=recommendations, training_plans=plans)

    decided = handler.handle(user_id="user-1", recommendation_id=saved.id, accepted_at=date(2027, 1, 28))

    assert decided is not None
    assert decided.decision == "accepted"
    assert plans.plan is not None
    assert plans.plan.status == "active"
    assert plans.activated_draft_ids == ["draft-plan-1"]


def test_rejecting_training_plan_creation_leaves_draft_inactive() -> None:
    recommendations = FakeRecommendationStore()
    saved = recommendations.create_recommendation("user-1", _training_plan_creation_recommendation())
    plans = FakeTrainingPlanStore(_draft_plan())
    handler = RejectRecommendationHandler(recommendations=recommendations)

    decided = handler.handle(user_id="user-1", recommendation_id=saved.id)

    assert decided is not None
    assert decided.decision == "rejected"
    assert plans.plan is not None
    assert plans.plan.status == "draft"


def test_accepting_stale_or_cross_user_recommendation_does_not_mutate_plan() -> None:
    recommendations = FakeRecommendationStore()
    saved = recommendations.create_recommendation("user-1", _recommendation(duration=30))
    stale_plan = _plan(_workout(duration=40))
    plans = FakeTrainingPlanStore(stale_plan)
    handler = AcceptRecommendationHandler(recommendations=recommendations, training_plans=plans)

    stale_result = handler.handle(user_id="user-1", recommendation_id=saved.id)
    cross_user_result = handler.handle(user_id="user-2", recommendation_id=saved.id)

    assert stale_result is None
    assert cross_user_result is None
    assert plans.plan is not None
    assert plans.plan.workouts[0].planned_duration_minutes == 40
    assert recommendations.recommendations[saved.id].status == "pending"


def test_reject_and_edit_preserve_plan_and_recommendation_history() -> None:
    recommendations = FakeRecommendationStore()
    rejected = recommendations.create_recommendation("user-1", _recommendation(duration=30))
    edited = recommendations.create_recommendation("user-1", _recommendation(duration=30))
    plans = FakeTrainingPlanStore(_plan())
    reject_handler = RejectRecommendationHandler(recommendations=recommendations)
    edit_handler = EditRecommendationHandler(recommendations=recommendations)

    reject_result = reject_handler.handle(user_id="user-1", recommendation_id=rejected.id)
    revised = edit_handler.handle(
        user_id="user-1",
        recommendation_id=edited.id,
        revised_action=_recommendation(duration=20).proposed_action,
    )

    assert reject_result is not None
    assert reject_result.decision == "rejected"
    assert plans.plan is not None
    assert plans.plan.workouts[0].planned_duration_minutes == 45
    assert revised is not None
    assert recommendations.recommendations[edited.id].decision == "edited"
    assert revised.status == "pending"
    assert revised.proposed_action.payload["after_payload"]["planned_duration_minutes"] == 20
    assert revised.proposed_action.payload["supersedes_recommendation_id"] == edited.id


def test_create_daily_recommendation_handler_creates_recovery_warning_without_llm_text() -> None:
    recommendations = FakeRecommendationStore()
    handler = CreateDailyRecommendationHandler(recommendations=recommendations)

    created = handler.handle(user_id="user-1", today_context=_today_context())

    assert created is not None
    assert created.status == "pending"
    assert created.recommendation_type == "workout_adjustment"
    assert created.proposed_action.action_type == "adjust_workout"
    assert created.evidence[0].metric == "readiness_label"
    assert "LLM" not in created.rationale


def test_create_daily_recommendation_handler_skips_insufficient_context() -> None:
    recommendations = FakeRecommendationStore()
    handler = CreateDailyRecommendationHandler(recommendations=recommendations)

    no_workout = handler.handle(
        user_id="user-1",
        today_context=_today_context(scheduled_workouts=()),
    )
    ready = handler.handle(
        user_id="user-1",
        today_context=_today_context(readiness="ready"),
    )

    assert no_workout is None
    assert ready is None
    assert recommendations.recommendations == {}
