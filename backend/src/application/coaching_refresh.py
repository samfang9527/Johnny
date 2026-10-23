"""Transactional invalidation and durable correction intents for coaching evidence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.application.async_agent_runs import QueueAgentRunHandler
from src.application.coaching_analysis_evidence import build_coaching_evidence
from src.application.coaching_generation_requests import CoachingGenerationRequests
from src.domain.integrations_notifications import SyncSummary
from src.infrastructure.database.agent_run_repository import SqlAlchemyAgentRunRepository
from src.infrastructure.database.agent_task_queue import SqlAlchemyAgentTaskQueue
from src.infrastructure.database.coaching_repository import SqlAlchemyCoachingRepository
from src.infrastructure.database.coaching_analysis_evidence_repository import SqlAlchemyCoachingAnalysisEvidenceRepository
from src.infrastructure.database.models import (
    ActivityDetailBatchModel, ActivityModel, AgentRunModel, AgentTaskModel,
    AthleteProfileModel,
    CoachingGenerationRequestModel,
    RecommendationModel, TrainingReviewModel,
    TrainingReviewRevisionModel, WorkoutAdviceModel, WorkoutAdviceRevisionModel,
)
from src.infrastructure.llm.settings import resolve_queued_training_plan_provider


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
        provider, model = resolve_queued_training_plan_provider()
        queued = QueueAgentRunHandler(
            runs=runs, queue=tasks, prompt_version="johnny-review-analysis-v1",
            provider=provider, model=model,
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
                      source_sync_run_id: str | None = None,
                      queue_auto_reviews: bool = True,
                      bump_version: bool = True,
                      as_of: datetime | None = None) -> RefreshEffects:
        """Call in the same transaction as the evidence write, once per logical batch."""
        if not changed_dates and not affects_advice:
            return RefreshEffects()
        if bump_version:
            self.coaching.bump_input_version(user_id)
        else:
            self.coaching._lock_owner_version(user_id)
        observed_at = as_of or datetime.now(timezone.utc)
        reviews = self.session.scalars(select(TrainingReviewModel).where(
            TrainingReviewModel.user_id == user_id,
            TrainingReviewModel.current_revision_id.is_not(None),
        ).with_for_update()).all()
        review_runs: list[str] = []
        affected = []
        for review in reviews:
            if not any(review.starts_on <= day <= review.ends_on for day in changed_dates):
                continue
            bundle = build_coaching_evidence(user_id=user_id, kind='daily_review',
                local_date=review.publication_date, timezone_name=review.timezone_name,
                workout_id=None, constraints=None, as_of=observed_at,
                store=SqlAlchemyCoachingAnalysisEvidenceRepository(self.session))
            current = self.session.get(TrainingReviewRevisionModel, review.current_revision_id)
            prior = (current.payload or {}).get('evidence_fingerprint') if current else None
            if prior == bundle.fingerprint:
                continue
            review.freshness = "stale"
            if review.publication_date == exclude_review_date:
                continue
            affected.append((review, bundle.fingerprint))
        if affected and queue_auto_reviews:
            review, fingerprint = max(affected, key=lambda pair: (pair[0].publication_date, pair[0].id))
            request_id = CoachingGenerationRequests(self.session).request(
                user_id=user_id, kind='daily_review', slot_id=review.id,
                fingerprint=fingerprint, reason=reason)
            if request_id:
                review_runs.append(self._queue_review_request(
                    review, request_id, fingerprint, reason, source_sync_run_id))
        advice_ids: list[str] = []
        recommendation_ids: list[str] = []
        invalidated_revision_ids: set[str] = set()
        if affects_advice:
            for advice in self.session.scalars(select(WorkoutAdviceModel).where(
                WorkoutAdviceModel.user_id == user_id,
                WorkoutAdviceModel.advice_date == today,
            ).with_for_update()):
                current = (self.session.get(WorkoutAdviceRevisionModel, advice.current_revision_id)
                           if advice.current_revision_id else None)
                prior = (current.payload or {}).get('evidence_fingerprint') if current else None
                if current and (current.payload or {}).get('evidence_manifest'):
                    payload = current.payload
                    from src.domain.workout_advice import WorkoutAdviceConstraints
                    try:
                        fresh = build_coaching_evidence(user_id=user_id, kind='workout_advice',
                            local_date=today, timezone_name=payload['timezone_name'],
                            workout_id=payload.get('workout_id'),
                            constraints=WorkoutAdviceConstraints(**payload['constraints']),
                            as_of=observed_at,
                            store=SqlAlchemyCoachingAnalysisEvidenceRepository(self.session))
                        if fresh.fingerprint == prior:
                            continue
                    except (KeyError, LookupError, TypeError, ValueError):
                        pass
                elif changed_dates and not any(today - timedelta(days=28) <= day <= today
                                               for day in changed_dates):
                    continue
                advice.freshness = "stale"
                advice_ids.append(advice.id)
                if advice.current_revision_id:
                    invalidated_revision_ids.add(advice.current_revision_id)
            for proposal in self.session.scalars(select(RecommendationModel).where(
                RecommendationModel.user_id == user_id,
                RecommendationModel.status == "pending",
                RecommendationModel.source_advice_revision_id.in_(invalidated_revision_ids),
            ).with_for_update()):
                proposal.status = "superseded"
                proposal.invalidation_reason = reason
                recommendation_ids.append(proposal.id)
        self.session.flush()
        return RefreshEffects(tuple(review_runs), tuple(advice_ids), tuple(recommendation_ids))

    def _queue_review_request(self, review: TrainingReviewModel, request_id: str,
                              fingerprint: str, reason: str,
                              source_sync_run_id: str | None = None) -> str:
        provider, model = resolve_queued_training_plan_provider()
        queue = QueueAgentRunHandler(
            runs=SqlAlchemyAgentRunRepository(self.session),
            queue=SqlAlchemyAgentTaskQueue(self.session),
            prompt_version='johnny-review-analysis-v1', provider=provider, model=model)
        result = queue.queue_run(user_id=review.user_id, workflow_name='daily_review',
            trigger_type='evidence_change', idempotency_key=f'review-correction:{request_id}',
            payload={'publication_date': review.publication_date.isoformat(),
                     'timezone_name': review.timezone_name, 'revision_reason': reason,
                     'generation_request_id': request_id, 'evidence_fingerprint': fingerprint,
                     **({'source_sync_run_id': source_sync_run_id} if source_sync_run_id else {})},
            task_type='agent.workflow')
        CoachingGenerationRequests(self.session).bind_run(request_id=request_id, run_id=result.run.id)
        task = self.session.get(AgentTaskModel, result.task.id)
        if task is not None:
            task.available_at = datetime.now(timezone.utc) + timedelta(seconds=5)
        return result.run.id

    def finish_review_request(self, request_id: str, completed_fingerprint: str) -> str | None:
        requests = CoachingGenerationRequests(self.session)
        row = self._lock_active_review_request(request_id, requests)
        if row is None or row.kind != 'daily_review':
            return None
        slot = self.session.scalar(select(TrainingReviewModel).where(
            TrainingReviewModel.id == row.slot_id,
            TrainingReviewModel.user_id == row.user_id).with_for_update())
        successor = requests.finish(request_id=request_id,
                                    completed_fingerprint=completed_fingerprint)
        if successor and slot is not None:
            active = requests.get_active(successor)
            return self._queue_review_request(slot, successor,
                active.active_fingerprint, active.reason)
        return None

    def fail_review_request(self, request_id: str) -> str | None:
        requests = CoachingGenerationRequests(self.session)
        row = self._lock_active_review_request(request_id, requests)
        if row is None or row.kind != 'daily_review':
            return None
        slot = self.session.scalar(select(TrainingReviewModel).where(
            TrainingReviewModel.id == row.slot_id,
            TrainingReviewModel.user_id == row.user_id).with_for_update())
        successor = requests.fail(request_id=request_id)
        if successor and slot is not None:
            active = requests.get_active(successor)
            return self._queue_review_request(slot, successor,
                active.active_fingerprint, active.reason)
        return None

    def reconcile_changed_review_request(self, request_id: str) -> str | None:
        requests = CoachingGenerationRequests(self.session)
        row = self._lock_active_review_request(request_id, requests)
        if row is None or row.kind != 'daily_review':
            return None
        slot = self.session.scalar(select(TrainingReviewModel).where(
            TrainingReviewModel.id == row.slot_id,
            TrainingReviewModel.user_id == row.user_id))
        if slot is None:
            return None
        current = build_coaching_evidence(user_id=row.user_id, kind='daily_review',
            local_date=slot.publication_date, timezone_name=slot.timezone_name,
            workout_id=None, constraints=None, as_of=datetime.now(timezone.utc),
            store=SqlAlchemyCoachingAnalysisEvidenceRepository(self.session))
        requests.request(user_id=row.user_id, kind='daily_review', slot_id=slot.id,
                         fingerprint=current.fingerprint, reason='evidence_changed_during_generation')
        return self.fail_review_request(request_id)

    def _lock_active_review_request(self, request_id: str,
                                    requests: CoachingGenerationRequests) -> CoachingGenerationRequestModel | None:
        owner_id = self.session.scalar(select(CoachingGenerationRequestModel.user_id).where(
            CoachingGenerationRequestModel.active_request_id == request_id))
        if owner_id is None:
            return None
        # Match record_change's owner -> slot -> request lock order. The first
        # lookup is only a hint; recheck the active ID under the row lock.
        self.coaching._lock_owner_version(owner_id)
        return requests.get_active(request_id)

    def complete_detail_batch(self, *, batch_id: str, changed_activity_ids: tuple[str, ...],
                              now: datetime) -> RefreshEffects:
        batch = self.session.scalar(select(ActivityDetailBatchModel).where(
            ActivityDetailBatchModel.id == batch_id).with_for_update())
        if batch is None or batch.status != 'closed':
            # Direct application calls may run while the finalizer is closing
            # in the same transaction; only an already closed batch publishes.
            return RefreshEffects()
        finalizer = self.session.scalar(select(AgentTaskModel).where(
            AgentTaskModel.idempotency_key == f'activity.detail.finalize.v1:{batch_id}'))
        payload = finalizer.payload or {} if finalizer else {}
        profile_timezone = self.session.scalar(select(AthleteProfileModel.timezone).where(
            AthleteProfileModel.user_id == batch.user_id))
        timezone_name = payload.get('coaching_timezone_name') or profile_timezone or 'UTC'
        zone = ZoneInfo(timezone_name)
        today = date.fromisoformat(payload['coaching_today']) if payload.get('coaching_today') else now.astimezone(zone).date()
        changed_dates = {date.fromisoformat(value)
                         for value in payload.get('coaching_changed_dates') or ()}
        activities = self.session.scalars(select(ActivityModel).where(
            ActivityModel.user_id == batch.user_id,
            ActivityModel.id.in_(changed_activity_ids))).all() if changed_activity_ids else ()
        for activity in activities:
            local_day = activity.started_at.astimezone(zone).date() if activity.started_at.tzinfo else (
                activity.started_at.replace(tzinfo=timezone.utc).astimezone(zone).date())
            changed_dates.add(local_day)
        if changed_activity_ids:
            self._persist_batch_analyses(batch.user_id, tuple(activities), timezone_name, now)
        if not changed_dates:
            return RefreshEffects()
        return self.record_change(user_id=batch.user_id, changed_dates=changed_dates,
            today=today, reason='detail_batch_closed',
            affects_advice=bool(changed_activity_ids) and any(
                today - timedelta(days=28) <= day <= today for day in changed_dates),
            bump_version=bool(changed_activity_ids), as_of=now)

    def _persist_batch_analyses(self, user_id: str, activities: tuple[ActivityModel, ...],
                                timezone_name: str, as_of: datetime) -> None:
        from src.application.coaching_evidence import build_review_evidence, matched_execution_inputs
        from src.domain.activity_execution import analyze_execution
        from src.domain.training_review import review_period
        from src.infrastructure.database.activity_detail_repository import SqlAlchemyActivityDetailRepository
        from src.infrastructure.database.activity_repository import SqlAlchemyActivityRepository
        details_store = SqlAlchemyActivityDetailRepository(self.session)
        activities_store = SqlAlchemyActivityRepository(self.session)
        zone = ZoneInfo(timezone_name)
        processed: set[str] = set()
        for model in activities:
            if model.id in processed:
                continue
            if not model.duration_seconds or model.duration_seconds <= 0:
                # Legacy provider stubs can have a detail fetch before a usable
                # activity summary; retain the snapshot but defer interpretation.
                continue
            recording = activities_store.get_activity_for_user(user_id, model.id)
            snapshots = details_store.get_snapshots(user_id, model.id)
            if recording is None or not snapshots:
                continue
            local_day = (recording.started_at.replace(tzinfo=timezone.utc)
                         if recording.started_at.tzinfo is None else recording.started_at).astimezone(zone).date()
            evidence = build_review_evidence(user_id=user_id,
                period=review_period(local_day + timedelta(days=1)),
                timezone_name=timezone_name, as_of=as_of, store=self.coaching)
            match = next((item for item in matched_execution_inputs(evidence)
                          if any(a.id == model.id for a in item.activities)), None)
            group = match.activities if match else (recording,)
            group_snapshots = tuple(s for activity in group
                                    for s in details_store.get_snapshots(user_id, activity.id))
            owned = self.session.scalars(select(ActivityModel.id).where(
                ActivityModel.user_id == user_id,
                ActivityModel.id.in_(a.id for a in group),
                ActivityModel.provider_connection_id.is_not(None))).all()
            if len(owned) != len(group) or any(not details_store.get_snapshots(user_id, a.id) for a in group):
                match = None
                group = (recording,)
                group_snapshots = snapshots
            analysis = analyze_execution(prescription=match.prescription if match else None,
                                         activities=group, details=group_snapshots)
            details_store.save_analysis(user_id, analysis)
            processed.update(a.id for a in group)

    def record_sync(self, *, user_id: str, summary: SyncSummary, today: date,
                    timezone_name: str,
                    exclude_review_date: date | None = None,
                    source_sync_run_id: str | None = None,
                    as_of: datetime | None = None) -> RefreshEffects:
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
        batch = (self.session.scalar(select(ActivityDetailBatchModel).where(
            ActivityDetailBatchModel.user_id == user_id,
            ActivityDetailBatchModel.source_sync_run_id == source_sync_run_id,
            ActivityDetailBatchModel.status.in_(('pending', 'paused'))))
            if source_sync_run_id else None)
        if batch is not None:
            finalizer = self.session.scalar(select(AgentTaskModel).where(
                AgentTaskModel.idempotency_key == f'activity.detail.finalize.v1:{batch.id}').with_for_update())
            if finalizer is not None:
                prior = set((finalizer.payload or {}).get('coaching_changed_dates') or ())
                finalizer.payload = {**(finalizer.payload or {}),
                    'coaching_changed_dates': sorted(prior | {d.isoformat() for d in dates}),
                    'coaching_today': today.isoformat(),
                    'coaching_timezone_name': timezone_name}
        changed = self.record_change(user_id=user_id, changed_dates=dates, today=today,
                                     reason="provider_evidence_changed", affects_advice=bool(stored or stored_health),
                                     exclude_review_date=exclude_review_date,
                                     source_sync_run_id=source_sync_run_id,
                                     queue_auto_reviews=batch is None, as_of=as_of)
        return RefreshEffects(
            review_run_ids=((recovered,) if recovered else ()) + changed.review_run_ids,
            invalidated_advice_ids=changed.invalidated_advice_ids,
            superseded_recommendation_ids=changed.superseded_recommendation_ids,
        )
