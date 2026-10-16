"""Generate requested same-day guidance and publish bounded workout proposals."""

from __future__ import annotations

from dataclasses import asdict
from datetime import date, datetime, time, timedelta, timezone
from typing import Callable
from zoneinfo import ZoneInfo

from src.application.training_analytics import resolve_plan_for_date
from src.domain.activity_sessions import match_sessions, utc
from src.domain.coaching_fingerprints import canonical_fingerprint
from src.domain.recommendation_approval import EvidenceItem, ProposedAction, Recommendation
from src.domain.workout_advice import AdviceEvidence, WorkoutAdviceConstraints, assess_workout_advice


class GenerateWorkoutAdviceHandler:
    def __init__(self, *, coaching, plans, activities,
                 now: Callable[[], datetime] | None = None) -> None:
        self._coaching = coaching
        self._plans = plans
        self._activities = activities
        self._now = now or (lambda: datetime.now(timezone.utc))

    def handle(self, *, user_id: str, advice_date: date, timezone_name: str,
               workout_id: str | None, constraints: WorkoutAdviceConstraints,
               run_id: str, activity_sync_usable: bool) -> dict:
        zone = ZoneInfo(timezone_name)
        now = self._now()
        if now.astimezone(zone).date() != advice_date:
            raise ValueError("request_date_expired")
        plan = (self._plans.get_plan_for_date_raw(user_id, advice_date)
                if hasattr(self._plans, "get_plan_for_date_raw")
                else resolve_plan_for_date(self._plans, user_id, advice_date))
        workouts = tuple(item for item in plan.workouts if item.scheduled_for == advice_date) if plan else ()
        if workout_id is None and len(workouts) > 1:
            raise ValueError("workout_choice_required")
        workout = next((item for item in workouts if item.id == workout_id), None) if workout_id else (workouts[0] if workouts else None)
        if workout_id is not None and workout is None:
            raise LookupError("workout not found for today")
        slot_key = workout.id if workout and workout.id else "no-workout"
        reservation = self._coaching.reserve_advice(user_id, advice_date, slot_key, run_id,
                                                     asdict(constraints))
        recordings = tuple(
            item for item in self._activities.list_activities_for_user_between(
                user_id, advice_date - timedelta(days=1), advice_date + timedelta(days=1),
            ) if utc(item.started_at).astimezone(zone).date() == advice_date
            and utc(item.started_at) <= utc(now)
        )
        sessions = match_sessions(recordings, workouts, timezone_name)
        facts = AdviceEvidence(
            timezone_name=timezone_name,
            matched_today=bool(workout and any(item.workout_id == workout.id for item in sessions)),
            unresolved_today=bool(workout and any(item.status == "needs_review" for item in sessions)),
            activity_sync_usable=activity_sync_usable,
        )
        decision = assess_workout_advice(workout=workout, evidence=facts,
                                         constraints=constraints, now=now)
        before = workout.to_payload() if workout else None
        after = decision.after_workout.to_payload() if decision.after_workout else None
        evidence_fingerprint = canonical_fingerprint({
            "date": advice_date, "timezone": timezone_name, "workout": before,
            "activities": [(item.id, item.started_at, item.duration_seconds,
                            item.distance_meters, item.matched_workout_id) for item in recordings],
            "constraints": asdict(constraints), "policy": decision.policy_version,
        })
        decision_fingerprint = canonical_fingerprint({
            "workout": before, "after": after, "constraints": asdict(constraints),
            "reason": decision.reason_code, "policy": decision.policy_version,
        })
        expires_at = datetime.combine(advice_date + timedelta(days=1), time.min,
                                       tzinfo=zone).astimezone(timezone.utc)
        payload = {
            "kind": "workout_advice", "advice_date": advice_date.isoformat(),
            "timezone_name": timezone_name, "workout_id": workout.id if workout else None,
            "constraints": asdict(constraints), "mode": decision.mode,
            "reason_code": decision.reason_code, "guidance": decision.guidance,
            "before": before, "after": after,
            "workout_fingerprint": canonical_fingerprint(before) if before else None,
            "evidence_fingerprint": evidence_fingerprint,
            "decision_fingerprint": decision_fingerprint,
            "generated_at": now.isoformat(), "expires_at": expires_at.isoformat(),
            "policy_version": decision.policy_version,
        }
        proposal = None
        if decision.after_workout is not None and plan is not None and workout is not None:
            proposal = Recommendation.create(
                user_id=user_id, recommendation_type="workout_adjustment", priority="medium",
                title="今日課表調整建議", rationale=decision.guidance,
                evidence=(EvidenceItem.create(source="johnny", metric="adjustment_reason",
                                              value=decision.reason_code),),
                proposed_action=ProposedAction.adjust_workout(
                    training_plan_id=plan.id, workout_id=workout.id,
                    before_payload=before, after_payload=after, reason=decision.guidance,
                ), training_plan_id=plan.id, workout_id=workout.id, agent_run_id=run_id,
            )
        if not self._coaching.publish_advice(reservation, payload, proposal):
            raise ValueError("advice inputs changed or a newer generation owns this workout")
        return self._coaching.get_advice_slot(user_id, advice_date, slot_key)["current"]
