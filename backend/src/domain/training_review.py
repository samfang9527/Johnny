"""Immutable dates and historical prescriptions for retrospective training reviews."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from src.domain.training_plan import Workout
from src.domain.activity_sessions import ActivitySession


@dataclass(frozen=True)
class ReviewPeriod:
    publication_date: date
    reviewed_date: date
    starts_on: date
    ends_on: date


def review_period(publication_date: date) -> ReviewPeriod:
    reviewed_date = publication_date - timedelta(days=1)
    return ReviewPeriod(
        publication_date=publication_date,
        reviewed_date=reviewed_date,
        starts_on=reviewed_date - timedelta(days=6),
        ends_on=reviewed_date,
    )


@dataclass(frozen=True)
class PrescriptionSnapshot:
    user_id: str
    plan_id: str
    workout_id: str
    workout: Workout
    effective_at: datetime
    source: str
    confidence: str
    recommendation_id: str | None = None


@dataclass(frozen=True)
class ReviewEvidence:
    period: ReviewPeriod
    timezone_name: str
    cutoff_at: datetime
    prescriptions: tuple[PrescriptionSnapshot, ...]
    sessions: tuple[ActivitySession, ...]
    covered_dates: frozenset[date]
    uncertainty_reasons: tuple[str, ...] = ()
