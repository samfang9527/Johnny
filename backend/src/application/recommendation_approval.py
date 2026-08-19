from __future__ import annotations

from datetime import date

from src.application.interfaces.recommendation_store import RecommendationStore
from src.application.interfaces.training_plan_store import TrainingPlanStore
from src.domain.recommendation_approval import EvidenceItem, ProposedAction, Recommendation
from src.domain.training_analytics import TodayContext
from src.domain.training_plan import PlanAdjustmentProposal, TrainingPlan, Workout


class AcceptRecommendationHandler:
    def __init__(
        self,
        *,
        recommendations: RecommendationStore,
        training_plans: TrainingPlanStore,
    ) -> None:
        self._recommendations = recommendations
        self._training_plans = training_plans

    def handle(self, *, user_id: str, recommendation_id: str | None) -> Recommendation | None:
        recommendation = self._recommendations.get_recommendation_for_user(user_id, recommendation_id)
        if recommendation is None:
            return None
        accepted = recommendation.accept()
        if recommendation.proposed_action.action_type == "no_plan_change":
            return self._recommendations.save_recommendation(user_id, accepted)
        if not _apply_workout_adjustment(user_id, accepted, self._training_plans):
            return None
        return self._recommendations.save_recommendation(user_id, accepted)


class RejectRecommendationHandler:
    def __init__(self, *, recommendations: RecommendationStore) -> None:
        self._recommendations = recommendations

    def handle(self, *, user_id: str, recommendation_id: str | None) -> Recommendation | None:
        recommendation = self._recommendations.get_recommendation_for_user(user_id, recommendation_id)
        if recommendation is None:
            return None
        return self._recommendations.save_recommendation(user_id, recommendation.reject())


class EditRecommendationHandler:
    def __init__(self, *, recommendations: RecommendationStore) -> None:
        self._recommendations = recommendations

    def handle(
        self,
        *,
        user_id: str,
        recommendation_id: str | None,
        revised_action: ProposedAction,
    ) -> Recommendation | None:
        recommendation = self._recommendations.get_recommendation_for_user(user_id, recommendation_id)
        if recommendation is None:
            return None
        edited, revised = recommendation.edit(revised_action)
        saved_edited = self._recommendations.save_recommendation(user_id, edited)
        if saved_edited is None:
            return None
        return self._recommendations.create_recommendation(user_id, revised)


class CreateDailyRecommendationHandler:
    def __init__(self, *, recommendations: RecommendationStore) -> None:
        self._recommendations = recommendations

    def handle(self, *, user_id: str, today_context: TodayContext) -> Recommendation | None:
        if today_context.user_id != user_id:
            return None
        if today_context.recovery.readiness_label != "rest":
            return None
        if not today_context.scheduled_workouts:
            return None

        before_payload = dict(today_context.scheduled_workouts[0])
        after_payload = {**before_payload, "status": "skipped"}
        training_plan_id = before_payload.get("training_plan_id") or _context_training_plan_id(today_context) or "plan-1"
        action = ProposedAction.adjust_workout(
            training_plan_id=training_plan_id,
            workout_id=before_payload["id"],
            before_payload=before_payload,
            after_payload=after_payload,
            reason="Recovery context indicates rest.",
        )
        recommendation = Recommendation.create(
            user_id=user_id,
            recommendation_type="workout_adjustment",
            priority="high",
            title="Skip today's workout",
            rationale="Recovery evidence indicates rest, so this recommendation proposes skipping today's workout.",
            evidence=(
                EvidenceItem.create(
                    source="training_analytics",
                    metric="readiness_label",
                    value=today_context.recovery.readiness_label,
                    observed_at=today_context.anchor_date.isoformat(),
                    summary="Recovery context indicates rest.",
                ),
            ),
            proposed_action=action,
            training_plan_id=action.payload["training_plan_id"],
            workout_id=action.payload["workout_id"],
        )
        return self._recommendations.create_recommendation(user_id, recommendation)


def _apply_workout_adjustment(
    user_id: str,
    recommendation: Recommendation,
    training_plans: TrainingPlanStore,
) -> bool:
    action = recommendation.proposed_action
    plan = training_plans.get_plan_for_user(user_id, action.payload.get("training_plan_id"))
    if plan is None:
        return False
    workout_id = action.payload.get("workout_id")
    current = next((workout for workout in plan.workouts if workout.id == workout_id), None)
    if current is None:
        return False
    if current.to_payload() != action.payload.get("before_payload"):
        return False

    updated_workout = _workout_from_payload(action.payload["after_payload"])
    updated_plan = _replace_workout(plan, updated_workout)
    adjustment = PlanAdjustmentProposal.create(
        user_id=user_id,
        training_plan_id=plan.id or action.payload["training_plan_id"],
        workout_id=workout_id,
        recommendation_id=recommendation.id,
        before_payload=action.payload["before_payload"],
        after_payload=action.payload["after_payload"],
    ).transition_to("approved").transition_to("applied")
    if training_plans.create_adjustment_proposal(user_id, adjustment) is None:
        return False
    training_plans.save_plan(user_id, updated_plan)
    return True


def _replace_workout(plan: TrainingPlan, updated_workout: Workout) -> TrainingPlan:
    return TrainingPlan.create(
        id=plan.id,
        user_id=plan.user_id,
        race_id=plan.race_id,
        name=plan.name,
        status=plan.status,
        starts_on=plan.starts_on,
        ends_on=plan.ends_on,
        workouts=tuple(updated_workout if workout.id == updated_workout.id else workout for workout in plan.workouts),
    )


def _workout_from_payload(payload: dict) -> Workout:
    scheduled_for = payload["scheduled_for"]
    if isinstance(scheduled_for, str):
        scheduled_for = date.fromisoformat(scheduled_for)
    pace_range = payload.get("pace_range_seconds_per_km")
    return Workout.create(
        id=payload.get("id"),
        scheduled_for=scheduled_for,
        workout_type=payload["workout_type"],
        purpose=payload["purpose"],
        planned_duration_minutes=payload.get("planned_duration_minutes"),
        planned_distance_meters=payload.get("planned_distance_meters"),
        pace_range_seconds_per_km=tuple(pace_range) if pace_range is not None else None,
        heart_rate_zone=payload.get("heart_rate_zone"),
        status=payload.get("status", "planned"),
    )


def _context_training_plan_id(today_context: TodayContext) -> str | None:
    evidence = today_context.training_load.evidence or {}
    value = evidence.get("training_plan_id")
    return str(value) if value else None
