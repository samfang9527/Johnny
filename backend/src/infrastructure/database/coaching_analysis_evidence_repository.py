"""Owner-scoped committed inputs for coaching evidence assembly."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.application.coaching_analysis_evidence import AdviceContext
from src.application.coaching_evidence import build_review_evidence
from src.domain.activity_execution import ExecutionAnalysis, ExecutionFact, ExecutionFinding
from src.domain.activity_sessions import match_sessions, utc
from src.domain.training_review import ReviewEvidence, review_period

from .activity_repository import SqlAlchemyActivityRepository
from .athlete_race_repository import SqlAlchemyAthleteRaceRepository
from .coaching_repository import SqlAlchemyCoachingRepository
from .models import ActivityDetailFetchModel, ActivityExecutionAnalysisModel, ActivityModel
from .training_plan_repository import SqlAlchemyTrainingPlanRepository


class SqlAlchemyCoachingAnalysisEvidenceRepository:
    def __init__(self, session: Session) -> None:
        self._session = session
        self._activities = SqlAlchemyActivityRepository(session)
        self._plans = SqlAlchemyTrainingPlanRepository(session)

    def load_review_evidence(self, user_id: str, publication_date: date,
                             timezone_name: str, as_of: datetime) -> ReviewEvidence:
        return build_review_evidence(user_id=user_id, period=review_period(publication_date),
                                     timezone_name=timezone_name, as_of=as_of,
                                     store=SqlAlchemyCoachingRepository(self._session))

    def load_advice_context(self, user_id: str, local_date: date, timezone_name: str,
                            workout_id: str | None, as_of: datetime) -> AdviceContext:
        zone = ZoneInfo(timezone_name)
        plan = self._plans.get_plan_for_date_raw(user_id, local_date)
        workouts = tuple(w for w in plan.workouts if w.scheduled_for == local_date) if plan else ()
        if workout_id is None and len(workouts) > 1:
            raise ValueError('workout_choice_required')
        workout = (next((w for w in workouts if w.id == workout_id), None)
                   if workout_id else (workouts[0] if workouts else None))
        if workout_id is not None and workout is None:
            raise LookupError('workout not found for today')
        recordings = tuple(a for a in self._activities.list_activities_for_user_between(
            user_id, local_date - timedelta(days=1), local_date + timedelta(days=1))
            if utc(a.started_at) <= utc(as_of)
            and utc(a.started_at).astimezone(zone).date() == local_date)
        today = match_sessions(recordings, workouts, timezone_name)
        next_workouts = tuple(sorted((w for w in plan.workouts
                                    if local_date < w.scheduled_for <= local_date + timedelta(days=7)
                                    and w.status == 'planned'),
                                   key=lambda w: (w.scheduled_for, w.id or '')))[:2] if plan else ()
        baseline = SqlAlchemyAthleteRaceRepository(self._session).get_profile_for_user(user_id)
        covered = SqlAlchemyCoachingRepository(self._session).covered_review_dates(
            user_id, local_date, local_date, timezone_name, as_of)
        return AdviceContext(plan, workout, today, baseline, next_workouts,
                             local_date in covered)

    def list_execution_analyses(self, user_id: str, starts_on: date,
                                ends_on: date, as_of: datetime) -> tuple[ExecutionAnalysis, ...]:
        # Widen the UTC query at both ends; the caller applies its athlete-local
        # timezone to each returned recording's started_at.
        rows = self._session.execute(select(ActivityExecutionAnalysisModel, ActivityModel).join(
            ActivityModel, ActivityExecutionAnalysisModel.activity_id == ActivityModel.id,
        ).where(ActivityExecutionAnalysisModel.user_id == user_id,
                ActivityModel.user_id == user_id,
                ActivityExecutionAnalysisModel.created_at <= utc(as_of),
                ActivityModel.started_at >= datetime.combine(starts_on - timedelta(days=1),
                                                              datetime.min.time(), tzinfo=utc(as_of).tzinfo),
                ActivityModel.started_at < datetime.combine(ends_on + timedelta(days=2),
                                                             datetime.min.time(), tzinfo=utc(as_of).tzinfo))
        .order_by(ActivityModel.started_at.desc(), ActivityExecutionAnalysisModel.created_at.desc(),
                  ActivityExecutionAnalysisModel.id.desc()))
        latest: dict[str, ExecutionAnalysis] = {}
        for model, activity in rows:
            if model.activity_id in latest:
                continue
            payload = model.payload
            latest[model.activity_id] = ExecutionAnalysis(
                activity_id=payload['activity_id'],
                activity_ids=tuple(payload['activity_ids']),
                fingerprint=payload['fingerprint'],
                prescription_revision_id=payload.get('prescription_revision_id'),
                snapshot_ids=tuple(payload.get('snapshot_ids') or ()),
                mapping=payload['mapping'],
                facts=tuple(ExecutionFact(id=item['id'], metric=item['metric'], value=item['value'],
                                          unit=item['unit'], scope=item['scope'],
                                          evidence_refs=tuple(item['evidence_refs']),
                                          denominator_seconds=item.get('denominator_seconds'),
                                          covered_seconds=item.get('covered_seconds'))
                            for item in payload.get('facts') or ()),
                findings=tuple(ExecutionFinding(code=item['code'], fact_ids=tuple(item['fact_ids']),
                                                supports=item['supports'],
                                                does_not_support=item['does_not_support'])
                               for item in payload.get('findings') or ()),
                limitations=tuple(payload.get('limitations') or ()),
                algorithm_version=payload.get('algorithm_version', model.algorithm_version),
                activity_started_at=utc(activity.started_at),
            )
        return tuple(latest.values())

    def list_recovery_metrics(self, user_id: str, starts_on: date, ends_on: date):
        return tuple(self._activities.list_daily_health_metrics_for_user_between(
            user_id, starts_on, ends_on))

    def list_current_detail_snapshots(self, user_id: str, starts_on: date,
                                      ends_on: date, as_of: datetime) -> tuple[dict, ...]:
        rows = self._session.execute(select(ActivityDetailFetchModel, ActivityModel).join(
            ActivityModel, ActivityDetailFetchModel.activity_id == ActivityModel.id).where(
            ActivityDetailFetchModel.user_id == user_id,
            ActivityModel.user_id == user_id,
            ActivityDetailFetchModel.current_snapshot_id.is_not(None),
            ActivityModel.started_at >= datetime.combine(starts_on - timedelta(days=1),
                                                          datetime.min.time(), tzinfo=utc(as_of).tzinfo),
            ActivityModel.started_at < datetime.combine(ends_on + timedelta(days=2),
                                                         datetime.min.time(), tzinfo=utc(as_of).tzinfo)))
        return tuple({'activity_id': activity.id, 'resource': fetch.resource,
                      'snapshot_id': fetch.current_snapshot_id,
                      'started_at': utc(activity.started_at)} for fetch, activity in rows)
