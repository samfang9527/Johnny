"""Transactional desired-state merge for one coaching publication slot."""

from __future__ import annotations

from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.infrastructure.database.models import CoachingGenerationRequestModel, UserModel


class CoachingGenerationRequests:
    def __init__(self, session: Session) -> None:
        self._session = session

    def request(self, *, user_id: str, kind: str, slot_id: str,
                fingerprint: str, reason: str) -> str | None:
        if kind not in ('daily_review', 'workout_advice') or not slot_id or len(fingerprint) != 64:
            raise ValueError('invalid coaching request identity')
        owner = self._session.scalar(select(UserModel.id).where(UserModel.id == user_id).with_for_update())
        if owner is None:
            raise LookupError('athlete not found')
        row = self._session.scalar(select(CoachingGenerationRequestModel).where(
            CoachingGenerationRequestModel.user_id == user_id,
            CoachingGenerationRequestModel.kind == kind,
            CoachingGenerationRequestModel.slot_id == slot_id).with_for_update())
        if row is None:
            attempt = str(uuid4())
            row = CoachingGenerationRequestModel(user_id=user_id, kind=kind, slot_id=slot_id,
                desired_fingerprint=fingerprint, active_fingerprint=fingerprint,
                active_request_id=attempt, reason=reason, status='queued')
            self._session.add(row)
            self._session.flush()
            return attempt
        row.desired_fingerprint = fingerprint
        row.reason = reason
        if row.active_request_id is not None or row.completed_fingerprint == fingerprint:
            self._session.flush()
            return None
        attempt = str(uuid4())
        row.active_request_id = attempt
        row.active_fingerprint = fingerprint
        row.active_run_id = None
        row.status = 'queued'
        self._session.flush()
        return attempt

    def bind_run(self, *, request_id: str, run_id: str) -> None:
        row = self._active(request_id)
        if row is None:
            raise LookupError('request is no longer active')
        row.active_run_id = run_id
        row.status = 'running'
        self._session.flush()

    def finish(self, *, request_id: str, completed_fingerprint: str) -> str | None:
        row = self._active(request_id)
        if row is None:
            return None
        row.completed_fingerprint = completed_fingerprint
        row.active_request_id = None
        row.active_run_id = None
        row.active_fingerprint = None
        if row.desired_fingerprint != completed_fingerprint:
            successor = str(uuid4())
            row.active_request_id = successor
            row.active_fingerprint = row.desired_fingerprint
            row.status = 'queued'
            self._session.flush()
            return successor
        row.status = 'completed'
        self._session.flush()
        return None

    def fail(self, *, request_id: str) -> str | None:
        """Release a terminal failure; preserve a newer desired input for one successor."""
        row = self._active(request_id)
        if row is None:
            return None
        failed_fingerprint = row.active_fingerprint
        row.active_request_id = None
        row.active_run_id = None
        row.active_fingerprint = None
        if row.desired_fingerprint != failed_fingerprint:
            successor = str(uuid4())
            row.active_request_id = successor
            row.active_fingerprint = row.desired_fingerprint
            row.status = 'queued'
            self._session.flush()
            return successor
        row.status = 'failed'
        self._session.flush()
        return None

    def get_active(self, request_id: str) -> CoachingGenerationRequestModel | None:
        return self._active(request_id)

    def _active(self, request_id: str) -> CoachingGenerationRequestModel | None:
        return self._session.scalar(select(CoachingGenerationRequestModel).where(
            CoachingGenerationRequestModel.active_request_id == request_id).with_for_update())
