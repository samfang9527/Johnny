"""Owner-locked, targeted acceptance of a Johnny workout proposal."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Callable
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.domain.activity_sessions import match_sessions, utc
from src.domain.coaching_fingerprints import canonical_fingerprint
from src.domain.training_plan import Workout
from src.infrastructure.database.activity_repository import SqlAlchemyActivityRepository
from src.infrastructure.database.coaching_repository import SqlAlchemyCoachingRepository
from src.infrastructure.database.models import (
    PlanAdjustmentModel, RecommendationModel, WorkoutAdviceModel, WorkoutAdviceRevisionModel,
)
from src.infrastructure.database.recommendation_repository import SqlAlchemyRecommendationRepository
from src.infrastructure.database.training_plan_repository import SqlAlchemyTrainingPlanRepository


class CoachingDecisionConflict(ValueError):
    pass


class CoachingApprovalService:
    def __init__(self, session: Session, now: Callable[[], datetime] | None = None) -> None:
        self._session = session
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._coaching = SqlAlchemyCoachingRepository(session)
        self._plans = SqlAlchemyTrainingPlanRepository(session)

    def accept(self, user_id: str, recommendation_id: str):
        self._coaching._lock_owner_version(user_id)
        model = self._recommendation(user_id, recommendation_id)
        if model is None:
            return None
        if model.status == "decided":
            if model.decision == "accepted":
                return self._as_domain(user_id, model.id)
            raise CoachingDecisionConflict("recommendation_already_rejected")
        if model.status != "pending":
            raise CoachingDecisionConflict("recommendation_not_actionable")
        revision, slot = self._current_source(user_id, model)
        payload = revision.payload
        now = self._now()
        zone = ZoneInfo(payload["timezone_name"])
        if (model.expires_at is None or utc(model.expires_at) <= utc(now)
                or payload["advice_date"] != now.astimezone(zone).date().isoformat()):
            model.status = "superseded"
            model.invalidation_reason = "expired"
            self._session.flush()
            raise CoachingDecisionConflict("recommendation_expired")
        before = payload.get("before")
        after = payload.get("after")
        if not isinstance(before, dict) or not isinstance(after, dict):
            raise CoachingDecisionConflict("recommendation_payload_invalid")
        if canonical_fingerprint(before) != model.workout_fingerprint:
            raise CoachingDecisionConflict("recommendation_payload_changed")
        action = (model.evidence or {}).get("proposed_action") or {}
        action_body = action.get("payload") if isinstance(action.get("payload"), dict) else action
        if (action_body.get("before_payload") != before or action_body.get("after_payload") != after):
            raise CoachingDecisionConflict("recommendation_preview_changed")
        plan_id = model.training_plan_id
        workout_id = before.get("id")
        advice_date = now.astimezone(zone).date()
        plan = self._plans.get_plan_for_date_raw(user_id, advice_date)
        if plan is None or plan.status != "active" or plan.id != plan_id:
            raise CoachingDecisionConflict("plan_changed")
        current = next((item for item in plan.workouts if item.id == workout_id), None)
        if current is None or current.status in {"completed", "skipped"}:
            raise CoachingDecisionConflict("workout_no_longer_actionable")
        activities = tuple(item for item in SqlAlchemyActivityRepository(self._session).list_activities_for_user_between(
            user_id, advice_date - timedelta(days=1), advice_date + timedelta(days=1),
        ) if utc(item.started_at).astimezone(zone).date() == advice_date)
        sessions = match_sessions(activities, tuple(item for item in plan.workouts if item.scheduled_for == advice_date),
                                  payload["timezone_name"])
        if any(item.workout_id == workout_id or item.status == "needs_review" for item in sessions):
            raise CoachingDecisionConflict("activity_started_or_unresolved")
        updated = Workout.from_payload(after)
        if not self._plans.update_workout_if_current(
            user_id, plan_id, workout_id, model.workout_fingerprint, updated,
        ):
            raise CoachingDecisionConflict("workout_changed")
        self._session.add(PlanAdjustmentModel(
            training_plan_id=plan_id, recommendation_id=model.id, status="applied",
            adjustment_payload={"user_id": user_id, "workout_id": workout_id,
                                "before_payload": before, "after_payload": after},
        ))
        self._coaching.record_prescription_revision(
            user_id=user_id, plan_id=plan_id, workout=updated, effective_at=now,
            source="approved_adjustment", confidence="known", recommendation_id=model.id,
        )
        model.status = "decided"
        model.decision = "accepted"
        model.decision_at = now
        slot.freshness = "stale"
        self._coaching.bump_input_version(user_id)
        self._session.flush()
        return self._as_domain(user_id, model.id)

    def reject(self, user_id: str, recommendation_id: str):
        self._coaching._lock_owner_version(user_id)
        model = self._recommendation(user_id, recommendation_id)
        if model is None:
            return None
        if model.status == "decided":
            if model.decision == "rejected":
                return self._as_domain(user_id, model.id)
            raise CoachingDecisionConflict("recommendation_already_accepted")
        if model.status != "pending":
            raise CoachingDecisionConflict("recommendation_not_actionable")
        self._current_source(user_id, model)
        model.status = "decided"
        model.decision = "rejected"
        model.decision_at = self._now()
        self._session.flush()
        return self._as_domain(user_id, model.id)

    def _recommendation(self, user_id: str, recommendation_id: str):
        return self._session.scalar(select(RecommendationModel).where(
            RecommendationModel.id == recommendation_id,
            RecommendationModel.user_id == user_id,
        ).with_for_update())

    def _current_source(self, user_id: str, model):
        if not model.source_advice_revision_id:
            raise CoachingDecisionConflict("workout_advice_required")
        revision = self._session.scalar(select(WorkoutAdviceRevisionModel).where(
            WorkoutAdviceRevisionModel.id == model.source_advice_revision_id,
            WorkoutAdviceRevisionModel.user_id == user_id,
        ))
        slot = self._session.scalar(select(WorkoutAdviceModel).where(
            WorkoutAdviceModel.id == revision.advice_id,
            WorkoutAdviceModel.user_id == user_id,
        ).with_for_update()) if revision else None
        if revision is None or slot is None or slot.current_revision_id != revision.id or slot.freshness == "stale":
            raise CoachingDecisionConflict("recommendation_stale")
        return revision, slot

    def _as_domain(self, user_id: str, recommendation_id: str):
        return SqlAlchemyRecommendationRepository(self._session).get_recommendation_for_user(
            user_id, recommendation_id,
        )
