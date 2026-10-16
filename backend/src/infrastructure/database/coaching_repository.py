"""Append-only prescription and plan activation history."""

from __future__ import annotations

from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.domain.training_plan import Workout
from src.domain.training_review import PrescriptionSnapshot
from .models import PlanActivationRevisionModel, WorkoutPrescriptionRevisionModel


class SqlAlchemyCoachingRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

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
            )
            for model in sorted(chosen.values(), key=lambda model: (model.scheduled_for, model.workout_id))
        )


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
