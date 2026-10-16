"""Transactional invalidation and durable correction intents for coaching evidence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.application.async_agent_runs import QueueAgentRunHandler
from src.domain.integrations_notifications import SyncSummary
from src.infrastructure.database.agent_run_repository import SqlAlchemyAgentRunRepository
from src.infrastructure.database.agent_task_queue import SqlAlchemyAgentTaskQueue
from src.infrastructure.database.coaching_repository import SqlAlchemyCoachingRepository
from src.infrastructure.database.models import (
    AgentTaskModel, RecommendationModel, TrainingReviewModel, WorkoutAdviceModel,
)


@dataclass(frozen=True)
class RefreshEffects:
    review_run_ids: tuple[str, ...] = ()
    invalidated_advice_ids: tuple[str, ...] = ()
    superseded_recommendation_ids: tuple[str, ...] = ()


class CoachingRefreshService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.coaching = SqlAlchemyCoachingRepository(session)

    def record_change(self, *, user_id: str, changed_dates: set[date],
                      today: date, reason: str, affects_advice: bool = True,
                      exclude_review_date: date | None = None) -> RefreshEffects:
        """Call in the same transaction as the evidence write, once per logical batch."""
        if not changed_dates and not affects_advice:
            return RefreshEffects()
        revision = self.coaching.bump_input_version(user_id)
        reviews = self.session.scalars(select(TrainingReviewModel).where(
            TrainingReviewModel.user_id == user_id,
            TrainingReviewModel.current_revision_id.is_not(None),
        ).with_for_update()).all()
        queue = QueueAgentRunHandler(
            runs=SqlAlchemyAgentRunRepository(self.session),
            queue=SqlAlchemyAgentTaskQueue(self.session),
            prompt_version="johnny-coaching-v1", provider="local",
            model="deterministic-local-companion",
        )
        review_runs: list[str] = []
        for review in reviews:
            if not any(review.starts_on <= day <= review.ends_on for day in changed_dates):
                continue
            review.freshness = "stale"
            if review.publication_date == exclude_review_date:
                continue
            result = queue.queue_run(
                user_id=user_id, workflow_name="daily_review", trigger_type="evidence_change",
                idempotency_key=f"review-correction:{review.id}:{revision}",
                payload={"publication_date": review.publication_date.isoformat(),
                         "timezone_name": review.timezone_name, "revision_reason": reason},
                task_type="coaching.sync",
            )
            task = self.session.get(AgentTaskModel, result.task.id)
            if task is not None:
                task.available_at = datetime.now(timezone.utc) + timedelta(seconds=5)
            review_runs.append(result.run.id)
        advice_ids: list[str] = []
        recommendation_ids: list[str] = []
        if affects_advice:
            for advice in self.session.scalars(select(WorkoutAdviceModel).where(
                WorkoutAdviceModel.user_id == user_id,
                WorkoutAdviceModel.advice_date == today,
            ).with_for_update()):
                advice.freshness = "stale"
                advice_ids.append(advice.id)
            for proposal in self.session.scalars(select(RecommendationModel).where(
                RecommendationModel.user_id == user_id,
                RecommendationModel.status == "pending",
                RecommendationModel.source_advice_revision_id.is_not(None),
            ).with_for_update()):
                proposal.status = "superseded"
                proposal.invalidation_reason = reason
                recommendation_ids.append(proposal.id)
        self.session.flush()
        return RefreshEffects(tuple(review_runs), tuple(advice_ids), tuple(recommendation_ids))

    def record_sync(self, *, user_id: str, summary: SyncSummary, today: date,
                    timezone_name: str,
                    exclude_review_date: date | None = None) -> RefreshEffects:
        stored = (summary.resources.get("activities") or {}).get("stored", 0)
        stored_health = any((bucket or {}).get("stored", 0) for name, bucket in summary.resources.items()
                            if name != "activities")
        dates: set[date] = set()
        coverage = summary.activity_coverage or {}
        if (coverage.get("timezone_name") == timezone_name
                and coverage.get("pagination_complete") is True
                and coverage.get("skipped_count", 0) == 0):
            try:
                first = date.fromisoformat(coverage["starts_on"])
                last = min(today - timedelta(days=1), date.fromisoformat(coverage["ends_on"]))
                current = max(first, today - timedelta(days=30))
                while current <= last:
                    dates.add(current)
                    current += timedelta(days=1)
            except (KeyError, ValueError, TypeError):
                pass
        if not stored and not stored_health:
            # Coverage only changes a review when it adds dates not in its published evidence.
            reviews = self.session.scalars(select(TrainingReviewModel).where(
                TrainingReviewModel.user_id == user_id,
                TrainingReviewModel.current_revision_id.is_not(None),
            )).all()
            newly_covered: set[date] = set()
            for review in reviews:
                slot = self.coaching.get_review_slot(user_id, review.publication_date)
                previous = set((slot or {}).get("current", {}).get("coverage", {}).get("covered_dates", []))
                newly_covered.update(day for day in dates if review.starts_on <= day <= review.ends_on
                                     and day.isoformat() not in previous)
            dates = newly_covered
        if stored_health or (stored and not dates):
            for review in self.session.scalars(select(TrainingReviewModel).where(
                TrainingReviewModel.user_id == user_id,
                TrainingReviewModel.current_revision_id.is_not(None),
            )):
                dates.add(review.ends_on)
        if not dates and not stored and not stored_health:
            return RefreshEffects()
        return self.record_change(user_id=user_id, changed_dates=dates, today=today,
                                  reason="provider_evidence_changed", affects_advice=bool(stored or stored_health),
                                  exclude_review_date=exclude_review_date)
