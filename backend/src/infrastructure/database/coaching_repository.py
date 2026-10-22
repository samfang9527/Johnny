"""Append-only prescription and plan activation history."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.domain.training_plan import Workout
from src.domain.training_review import GenerationReservation, PrescriptionSnapshot, review_period
from src.domain.coaching_fingerprints import canonical_fingerprint
from .activity_repository import SqlAlchemyActivityRepository
from .models import (
    IntegrationConnectionModel, PlanActivationRevisionModel, SyncRunModel,
    WorkoutPrescriptionRevisionModel, UserModel, CoachingInputVersionModel,
    TrainingReviewModel, TrainingReviewRevisionModel, WorkoutAdviceModel,
    WorkoutAdviceRevisionModel, RecommendationModel,
)


class SqlAlchemyCoachingRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def _lock_owner_version(self, user_id: str) -> CoachingInputVersionModel:
        owner = self._session.scalar(select(UserModel).where(UserModel.id == user_id).with_for_update())
        if owner is None:
            raise LookupError("athlete not found")
        row = self._session.get(CoachingInputVersionModel, user_id)
        if row is None:
            row = CoachingInputVersionModel(user_id=user_id, revision=0)
            self._session.add(row)
            self._session.flush()
        return row

    def bump_input_version(self, user_id: str) -> int:
        version = self._lock_owner_version(user_id)
        version.revision += 1
        self._session.flush()
        return version.revision

    def reserve_review(self, user_id: str, publication_date: date, timezone_name: str,
                       run_id: str) -> GenerationReservation:
        ZoneInfo(timezone_name)
        version = self._lock_owner_version(user_id)
        slot = self._session.scalar(select(TrainingReviewModel).where(
            TrainingReviewModel.user_id == user_id,
            TrainingReviewModel.publication_date == publication_date,
        ).with_for_update())
        if slot is None:
            period = review_period(publication_date)
            slot = TrainingReviewModel(
                user_id=user_id, publication_date=publication_date,
                reviewed_date=period.reviewed_date, starts_on=period.starts_on,
                ends_on=period.ends_on, timezone_name=timezone_name,
                reserved_generation=0,
            )
            self._session.add(slot)
            self._session.flush()
        slot.reserved_generation += 1
        slot.reserved_run_id = run_id
        slot.timezone_name = timezone_name
        slot.attempt_state = "queued"
        slot.attempt_error = None
        self._session.flush()
        return GenerationReservation(user_id, "daily_review", slot.id,
                                     slot.reserved_generation, version.revision, run_id)

    def reserve_advice(self, user_id: str, advice_date: date, slot_key: str,
                       run_id: str, constraints: dict) -> GenerationReservation:
        if not slot_key:
            raise ValueError("non-null advice slot key is required")
        version = self._lock_owner_version(user_id)
        slot = self._session.scalar(select(WorkoutAdviceModel).where(
            WorkoutAdviceModel.user_id == user_id,
            WorkoutAdviceModel.advice_date == advice_date,
            WorkoutAdviceModel.slot_key == slot_key,
        ).with_for_update())
        if slot is None:
            slot = WorkoutAdviceModel(user_id=user_id, advice_date=advice_date,
                                      slot_key=slot_key, reserved_generation=0)
            self._session.add(slot)
            self._session.flush()
        slot.reserved_generation += 1
        slot.reserved_run_id = run_id
        slot.attempt_state = "queued"
        slot.attempt_error = None
        self._session.flush()
        return GenerationReservation(user_id, "workout_advice", slot.id,
                                     slot.reserved_generation, version.revision, run_id)

    def _current_reservation(self, reservation: GenerationReservation, kind: str):
        if reservation.workflow_kind != kind:
            raise ValueError("reservation workflow does not match publication")
        model_class = TrainingReviewModel if kind == "daily_review" else WorkoutAdviceModel
        slot = self._session.scalar(select(model_class).where(
            model_class.id == reservation.slot_id,
            model_class.user_id == reservation.user_id,
        ).with_for_update())
        if (slot is None or slot.reserved_generation != reservation.generation
                or slot.reserved_run_id != reservation.run_id):
            return None
        return slot

    def publish_review(self, reservation: GenerationReservation, revision: dict) -> bool:
        version = self._lock_owner_version(reservation.user_id)
        slot = self._current_reservation(reservation, "daily_review")
        if slot is None:
            return False
        if version.revision != reservation.input_revision:
            slot.attempt_state = "inputs_changed"
            self._session.flush()
            return False
        fingerprint = revision.get("fingerprint") or canonical_fingerprint(revision)
        existing = self._session.scalar(select(TrainingReviewRevisionModel).where(
            TrainingReviewRevisionModel.review_id == slot.id,
            TrainingReviewRevisionModel.content_fingerprint == fingerprint,
        ))
        if existing is None:
            existing = TrainingReviewRevisionModel(
                user_id=reservation.user_id, review_id=slot.id, run_id=reservation.run_id,
                content_fingerprint=fingerprint, input_revision=reservation.input_revision,
                payload=revision,
            )
            self._session.add(existing)
            self._session.flush()
        slot.current_revision_id = existing.id
        slot.attempt_state = "ready"
        slot.attempt_error = None
        slot.freshness = "current"
        self._session.flush()
        return True

    def publish_advice(self, reservation: GenerationReservation, revision: dict,
                       proposal=None) -> bool:
        version = self._lock_owner_version(reservation.user_id)
        slot = self._current_reservation(reservation, "workout_advice")
        if slot is None:
            return False
        if version.revision != reservation.input_revision:
            slot.attempt_state = "inputs_changed"
            self._session.flush()
            return False
        payload = dict(revision)
        if proposal is not None and self.was_decision_rejected(
            reservation.user_id, payload.get("decision_fingerprint")
        ):
            proposal = None
            payload["mode"] = "previously_declined"
            payload["reason_code"] = "previously_rejected"
            payload["guidance"] = f"{payload['guidance']} 你先前已婉拒這項相同調整，原課表維持不變。"
        if slot.current_revision_id:
            previous = self._session.get(WorkoutAdviceRevisionModel, slot.current_revision_id)
            previous_recommendation_id = (previous.payload or {}).get("recommendation_id") if previous else None
            if previous_recommendation_id:
                previous_recommendation = self._session.scalar(select(RecommendationModel).where(
                    RecommendationModel.id == previous_recommendation_id,
                    RecommendationModel.user_id == reservation.user_id,
                    RecommendationModel.status == "pending",
                ))
                if previous_recommendation is not None:
                    previous_recommendation.status = "superseded"
                    previous_recommendation.invalidation_reason = "newer_advice"
        if proposal is not None:
            from .recommendation_repository import SqlAlchemyRecommendationRepository
            if proposal.user_id != reservation.user_id:
                raise ValueError("proposal owner mismatch")
            saved = SqlAlchemyRecommendationRepository(self._session).create_recommendation(
                reservation.user_id, proposal,
            )
            payload["recommendation_id"] = saved.id
        item = WorkoutAdviceRevisionModel(
            user_id=reservation.user_id, advice_id=slot.id, run_id=reservation.run_id,
            content_fingerprint=payload.get("fingerprint") or canonical_fingerprint(payload),
            input_revision=reservation.input_revision, payload=payload,
        )
        self._session.add(item)
        self._session.flush()
        if proposal is not None:
            recommendation_model = self._session.scalar(select(RecommendationModel).where(
                RecommendationModel.id == payload["recommendation_id"],
                RecommendationModel.user_id == reservation.user_id,
            ))
            recommendation_model.source_advice_revision_id = item.id
            recommendation_model.workout_fingerprint = payload.get("workout_fingerprint")
            recommendation_model.evidence_fingerprint = payload.get("evidence_fingerprint")
            recommendation_model.decision_fingerprint = payload.get("decision_fingerprint")
            if payload.get("expires_at"):
                recommendation_model.expires_at = datetime.fromisoformat(payload["expires_at"])
        slot.current_revision_id = item.id
        slot.attempt_state = "ready"
        slot.attempt_error = None
        slot.freshness = "current"
        self._session.flush()
        return True

    def was_decision_rejected(self, user_id: str, fingerprint: str | None) -> bool:
        if not fingerprint:
            return False
        return self._session.scalar(select(RecommendationModel.id).where(
            RecommendationModel.user_id == user_id,
            RecommendationModel.decision_fingerprint == fingerprint,
            RecommendationModel.decision == "rejected",
        ).limit(1)) is not None

    def mark_attempt_failed(self, reservation: GenerationReservation, state: str,
                            reason_code: str) -> None:
        slot = self._current_reservation(reservation, reservation.workflow_kind)
        if slot is not None:
            slot.attempt_state = state
            slot.attempt_error = reason_code
            self._session.flush()

    def get_review_slot(self, user_id: str, publication_date: date) -> dict | None:
        slot = self._session.scalar(select(TrainingReviewModel).where(
            TrainingReviewModel.user_id == user_id,
            TrainingReviewModel.publication_date == publication_date,
        ))
        if slot is None:
            return None
        current = self._session.get(TrainingReviewRevisionModel, slot.current_revision_id) if slot.current_revision_id else None
        return {"id": slot.id, "publication_date": slot.publication_date.isoformat(),
                "attempt_state": slot.attempt_state, "attempt_error": slot.attempt_error,
                "freshness": slot.freshness, "revision_id": slot.current_revision_id,
                "reserved_run_id": slot.reserved_run_id,
                "current": current.payload if current else None}

    def get_advice_slot(self, user_id: str, advice_date: date, slot_key: str) -> dict | None:
        slot = self._session.scalar(select(WorkoutAdviceModel).where(
            WorkoutAdviceModel.user_id == user_id,
            WorkoutAdviceModel.advice_date == advice_date,
            WorkoutAdviceModel.slot_key == slot_key,
        ))
        if slot is None:
            return None
        current = self._session.get(WorkoutAdviceRevisionModel, slot.current_revision_id) if slot.current_revision_id else None
        return {"id": slot.id, "advice_date": slot.advice_date.isoformat(),
                "slot_key": slot.slot_key, "attempt_state": slot.attempt_state,
                "attempt_error": slot.attempt_error, "freshness": slot.freshness,
                "revision_id": slot.current_revision_id, "reserved_run_id": slot.reserved_run_id,
                "current": current.payload if current else None}

    def list_review_activities(self, user_id: str, starts_on: date, ends_on: date):
        return tuple(SqlAlchemyActivityRepository(self._session).list_activities_for_user_between(
            user_id, starts_on, ends_on,
        ))

    def covered_review_dates(
        self, user_id: str, starts_on: date, ends_on: date,
        timezone_name: str, as_of: datetime,
    ) -> frozenset[date]:
        ZoneInfo(timezone_name)
        runs = self._session.scalars(
            select(SyncRunModel).join(
                IntegrationConnectionModel,
                SyncRunModel.integration_connection_id == IntegrationConnectionModel.id,
            ).where(
                IntegrationConnectionModel.user_id == user_id,
                SyncRunModel.finished_at.is_not(None),
                SyncRunModel.finished_at <= _utc(as_of),
            )
        )
        days: set[date] = set()
        for run in runs:
            summary = run.summary or {}
            coverage = summary.get("activity_coverage") or {}
            bucket = (summary.get("resources") or {}).get("activities") or {}
            if (coverage.get("timezone_name") != timezone_name
                    or coverage.get("pagination_complete") is not True
                    or coverage.get("skipped_count", 0) != 0
                    or bucket.get("failed", 0) != 0):
                continue
            try:
                first = max(starts_on, date.fromisoformat(coverage["starts_on"]))
                last = min(ends_on, date.fromisoformat(coverage["ends_on"]))
            except (KeyError, TypeError, ValueError):
                continue
            current = first
            while current <= last:
                days.add(current)
                current += timedelta(days=1)
        return frozenset(days)

    def record_plan_activation(
        self, *, user_id: str, plan_id: str, effective_at: datetime,
        effective_local_date: date, timezone_name: str, previous_plan_id: str | None,
    ) -> str:
        if effective_at.tzinfo is None:
            raise ValueError("effective timestamp needs timezone")
        ZoneInfo(timezone_name)
        model = PlanActivationRevisionModel(
            user_id=user_id, plan_id=plan_id, previous_plan_id=previous_plan_id,
            effective_at=effective_at.astimezone(timezone.utc),
            effective_local_date=effective_local_date, timezone_name=timezone_name,
        )
        self._session.add(model)
        self._session.flush()
        return model.id

    def record_prescription_revision(
        self, *, user_id: str, plan_id: str, workout: Workout, effective_at: datetime,
        source: str, confidence: str, recommendation_id: str | None,
    ) -> str:
        if workout.id is None:
            raise ValueError("persisted workout id is required")
        if effective_at.tzinfo is None:
            raise ValueError("effective timestamp needs timezone")
        if source not in {"generation", "approved_adjustment", "legacy_backfill"}:
            raise ValueError("unknown prescription source")
        if confidence not in {"known", "legacy_uncertain"}:
            raise ValueError("unknown prescription confidence")
        model = WorkoutPrescriptionRevisionModel(
            user_id=user_id, plan_id=plan_id, workout_id=workout.id,
            scheduled_for=workout.scheduled_for, effective_at=effective_at.astimezone(timezone.utc),
            workout_payload=workout.to_payload(), source=source, confidence=confidence,
            recommendation_id=recommendation_id,
        )
        self._session.add(model)
        self._session.flush()
        return model.id

    def list_prescriptions(
        self, user_id: str, starts_on: date, ends_on: date,
        timezone_name: str, activity_starts: dict[str, datetime],
    ) -> tuple[PrescriptionSnapshot, ...]:
        zone = ZoneInfo(timezone_name)
        activations = tuple(self._session.scalars(
            select(PlanActivationRevisionModel).where(
                PlanActivationRevisionModel.user_id == user_id,
                PlanActivationRevisionModel.effective_local_date <= ends_on,
            )
        ))
        revisions = tuple(self._session.scalars(
            select(WorkoutPrescriptionRevisionModel).where(
                WorkoutPrescriptionRevisionModel.user_id == user_id,
                WorkoutPrescriptionRevisionModel.scheduled_for >= starts_on,
                WorkoutPrescriptionRevisionModel.scheduled_for <= ends_on,
            )
        ))
        chosen: dict[str, WorkoutPrescriptionRevisionModel] = {}
        for candidate in revisions:
            owners = sorted(
                (a for a in activations if a.effective_local_date <= candidate.scheduled_for),
                key=lambda a: (a.effective_local_date, _utc(a.effective_at), a.id),
            )
            if not owners or owners[-1].plan_id != candidate.plan_id:
                continue
            start = activity_starts.get(candidate.workout_id)
            cutoff = _utc(start) if start is not None else datetime.combine(
                candidate.scheduled_for, time.max, tzinfo=zone,
            ).astimezone(timezone.utc)
            if _utc(candidate.effective_at) > cutoff and candidate.confidence != "legacy_uncertain":
                continue
            previous = chosen.get(candidate.workout_id)
            if previous is None or (_utc(candidate.effective_at), candidate.id) > (_utc(previous.effective_at), previous.id):
                chosen[candidate.workout_id] = candidate
        return tuple(
            PrescriptionSnapshot(
                user_id=user_id, plan_id=model.plan_id, workout_id=model.workout_id,
                workout=Workout.from_payload(model.workout_payload), effective_at=_utc(model.effective_at),
                source=model.source, confidence=model.confidence,
                recommendation_id=model.recommendation_id,
                revision_id=model.id,
            )
            for model in sorted(chosen.values(), key=lambda model: (model.scheduled_for, model.workout_id))
        )


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
