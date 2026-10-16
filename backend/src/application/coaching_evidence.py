"""Construct review facts from committed recordings and effective prescriptions."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Protocol
from zoneinfo import ZoneInfo

from src.domain.activity_health import CompletedActivity
from src.domain.activity_sessions import match_sessions, utc
from src.domain.training_review import PrescriptionSnapshot, ReviewEvidence, ReviewPeriod


class ReviewEvidenceStore(Protocol):
    def list_review_activities(self, user_id, starts_on, ends_on) -> tuple[CompletedActivity, ...]: ...
    def list_prescriptions(self, user_id, starts_on, ends_on, timezone_name, activity_starts) -> tuple[PrescriptionSnapshot, ...]: ...
    def covered_review_dates(self, user_id, starts_on, ends_on, timezone_name, as_of) -> frozenset: ...


def build_review_evidence(
    *, user_id: str, period: ReviewPeriod, timezone_name: str,
    as_of: datetime, store: ReviewEvidenceStore,
) -> ReviewEvidence:
    zone = ZoneInfo(timezone_name)
    cutoff = utc(as_of)
    recordings = tuple(
        activity for activity in store.list_review_activities(
            user_id, period.starts_on - timedelta(days=1), period.ends_on + timedelta(days=1)
        )
        if activity.user_id == user_id
        and utc(activity.started_at) <= cutoff
        and period.starts_on <= utc(activity.started_at).astimezone(zone).date() <= period.ends_on
    )
    starts: dict[str, datetime] = {}
    for activity in recordings:
        if activity.matched_workout_id:
            previous = starts.get(activity.matched_workout_id)
            instant = utc(activity.started_at)
            if previous is None or instant < previous:
                starts[activity.matched_workout_id] = instant
    prescriptions = store.list_prescriptions(
        user_id, period.starts_on, period.ends_on, timezone_name, starts,
    )
    sessions = match_sessions(recordings, tuple(p.workout for p in prescriptions), timezone_name)
    # Auto-matched recordings also establish the prescription effective at their start.
    for session in sessions:
        if session.workout_id and session.activities:
            instant = min(utc(a.started_at) for a in session.activities)
            if session.workout_id not in starts or instant < starts[session.workout_id]:
                starts[session.workout_id] = instant
    if starts:
        prescriptions = store.list_prescriptions(
            user_id, period.starts_on, period.ends_on, timezone_name, starts,
        )
        sessions = match_sessions(recordings, tuple(p.workout for p in prescriptions), timezone_name)
    covered = store.covered_review_dates(
        user_id, period.starts_on, period.ends_on, timezone_name, cutoff,
    )
    return ReviewEvidence(period, timezone_name, cutoff, prescriptions, sessions, covered)
