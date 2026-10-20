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
    AgentRunModel, AgentTaskModel, RecommendationModel, TrainingReviewModel, WorkoutAdviceModel,
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

    def recover_failed_review(self, *, user_id: str, publication_date: date,
                              timezone_name: str) -> str | None:
        """Repair an unstarted review rejected by a worker predating coaching.sync."""
        key = f"daily_review:{user_id}:{publication_date.isoformat()}"
        tasks = SqlAlchemyAgentTaskQueue(self.session)
        failed = tasks.get_by_idempotency_key(key)
        if (failed is None or failed.task_type != "coaching.sync" or failed.status != "failed"
                or failed.last_error_type != "UnknownTaskType"):
            return None
        runs = SqlAlchemyAgentRunRepository(self.session)
        previous = runs.get_run_for_user(user_id, failed.payload.get("run_id"))
        slot = self.coaching.get_review_slot(user_id, publication_date)
        if (previous is None or previous.status != "queued"
                or (slot is not None and (slot["current"] is not None
                    or slot["reserved_run_id"] != previous.id))):
            return None
        already_retried = self.session.scalar(select(AgentRunModel.id).where(
            AgentRunModel.user_id == user_id,
            AgentRunModel.workflow_name == "daily_review",
            AgentRunModel.correlation_id == previous.correlation_id,
            AgentRunModel.error_type == "WorkerVersionMismatch",
        ).limit(1)) is not None
        if already_retried:
            runs.fail_run(previous.fail(
                error_type="WorkerVersionMismatch",
                error_message="The active worker still cannot process coaching tasks",
            ))
            review = self.session.scalar(select(TrainingReviewModel).where(
                TrainingReviewModel.user_id == user_id,
                TrainingReviewModel.publication_date == publication_date,
            ).with_for_update())
            if review is not None:
                review.attempt_state = "sync_failed"
                review.attempt_error = "worker_version_mismatch"
                review.freshness = "stale"
            self.session.flush()
            return None
        runs.fail_run(previous.fail(
            error_type="WorkerVersionMismatch",
            error_message="A retired worker could not process this coaching task",
        ))
        queued = QueueAgentRunHandler(
            runs=runs, queue=tasks, prompt_version="johnny-coaching-v1",
            provider="local", model="deterministic-local-companion",
        ).queue_run(
            user_id=user_id, workflow_name="daily_review", trigger_type="scheduled",
            idempotency_key=key,
            payload={"publication_date": publication_date.isoformat(),
                     "timezone_name": timezone_name},
            task_type="coaching.sync", requeue_terminal=True,
        )
        self.coaching.reserve_review(user_id, publication_date, timezone_name, queued.run.id)
        return queued.run.id

    def record_change(self, *, user_id: str, changed_dates: set[date],
                      today: date, reason: str, affects_advice: bool = True,
                      exclude_review_date: date | None = None,
                      source_sync_run_id: str | None = None) -> RefreshEffects:
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
                         "timezone_name": review.timezone_name, "revision_reason": reason,
                         **({"source_sync_run_id": source_sync_run_id} if source_sync_run_id else {})},
                # Evidence and this task commit together. Corrections read that
                # stored evidence instead of launching another provider sync.
                task_type="agent.workflow",
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
                    exclude_review_date: date | None = None,
                    source_sync_run_id: str | None = None) -> RefreshEffects:
        recovered = self.recover_failed_review(
            user_id=user_id, publication_date=today, timezone_name=timezone_name)
        stored = (summary.resources.get("activities") or {}).get("stored", 0)
        stored_health = any((bucket or {}).get("stored", 0) for name, bucket in summary.resources.items()
                            if name != "activities")
        dates: set[date] = set()
        reviews = self.session.scalars(select(TrainingReviewModel).where(
            TrainingReviewModel.user_id == user_id,
            TrainingReviewModel.current_revision_id.is_not(None),
        )).all()
        coverage = summary.activity_coverage or {}
        if (coverage.get("timezone_name") == timezone_name
                and coverage.get("pagination_complete") is True
                and coverage.get("skipped_count", 0) == 0):
            try:
                first = date.fromisoformat(coverage["starts_on"])
                last = min(today - timedelta(days=1), date.fromisoformat(coverage["ends_on"]))
                for review in reviews:
                    slot = self.coaching.get_review_slot(user_id, review.publication_date)
                    previous = set((slot or {}).get("current", {}).get("coverage", {}).get("covered_dates", []))
                    current = max(first, review.starts_on)
                    end = min(last, review.ends_on)
                    while current <= end:
                        if current.isoformat() not in previous:
                            dates.add(current)
                        current += timedelta(days=1)
            except (KeyError, ValueError, TypeError):
                pass
        undated_stored = False
        for resource_type, bucket in summary.resources.items():
            count = int(bucket.get("stored", 0))
            if not count:
                continue
            recorded_dates = summary.stored_dates.get(resource_type, ())
            if len(recorded_dates) != count:
                undated_stored = True
                continue
            dates.update(date.fromisoformat(value) for value in recorded_dates)
        if undated_stored:
            for review in reviews:
                dates.add(review.ends_on)
        if not dates and not stored and not stored_health:
            return RefreshEffects(review_run_ids=(recovered,) if recovered else ())
        changed = self.record_change(user_id=user_id, changed_dates=dates, today=today,
                                     reason="provider_evidence_changed", affects_advice=bool(stored or stored_health),
                                     exclude_review_date=exclude_review_date,
                                     source_sync_run_id=source_sync_run_id)
        return RefreshEffects(
            review_run_ids=((recovered,) if recovered else ()) + changed.review_run_ids,
            invalidated_advice_ids=changed.invalidated_advice_ids,
            superseded_recommendation_ids=changed.superseded_recommendation_ids,
        )
