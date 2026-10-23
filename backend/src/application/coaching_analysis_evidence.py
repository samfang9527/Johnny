"""Bounded, dated facts shared by future coaching generation and currentness checks."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Literal, Protocol
from zoneinfo import ZoneInfo

from src.domain.activity_execution import ExecutionAnalysis
from src.domain.activity_health import DailyHealthMetrics
from src.domain.activity_sessions import ActivitySession, utc
from src.domain.athlete_race import AthleteProfile
from src.domain.coaching_fingerprints import canonical_fingerprint
from src.domain.training_plan import TrainingPlan, Workout
from src.domain.training_review import ReviewEvidence
from src.domain.workout_advice import WorkoutAdviceConstraints
from src.domain.workout_recovery import build_workout_recovery


@dataclass(frozen=True)
class AdviceContext:
    plan: TrainingPlan | None
    workout: Workout | None
    today_sessions: tuple[ActivitySession, ...]
    athlete_baseline: AthleteProfile | None
    next_workouts: tuple[Workout, ...]
    activity_sync_usable: bool = False


class CoachingAnalysisEvidenceStore(Protocol):
    def load_review_evidence(self, user_id: str, publication_date: date,
                             timezone_name: str, as_of: datetime) -> ReviewEvidence: ...
    def load_advice_context(self, user_id: str, local_date: date,
                            timezone_name: str, workout_id: str | None,
                            as_of: datetime) -> AdviceContext: ...
    def list_execution_analyses(self, user_id: str, starts_on: date,
                                ends_on: date, as_of: datetime) -> tuple[ExecutionAnalysis, ...]: ...
    def list_recovery_metrics(self, user_id: str, starts_on: date,
                              ends_on: date) -> tuple[DailyHealthMetrics, ...]: ...
    def list_current_detail_snapshots(self, user_id: str, starts_on: date,
                                      ends_on: date, as_of: datetime) -> tuple[dict, ...]: ...


@dataclass(frozen=True)
class CoachingEvidenceBundle:
    kind: Literal['daily_review', 'workout_advice']
    local_date: date
    timezone_name: str
    fingerprint: str
    manifest: dict


def _analysis_payload(analysis: ExecutionAnalysis) -> dict:
    findings = analysis.findings[:3]
    cited = {fact_id for finding in findings for fact_id in finding.fact_ids}
    payload = {
        'activity_ids': list(analysis.activity_ids), 'fingerprint': analysis.fingerprint,
        'prescription_revision_id': analysis.prescription_revision_id,
        'snapshot_ids': list(analysis.snapshot_ids), 'algorithm_version': analysis.algorithm_version,
        'mapping': analysis.mapping,
        'findings': [finding.to_payload() for finding in findings],
        'facts': [fact.to_payload() for fact in analysis.facts if fact.id in cited],
        'limitations': list(analysis.limitations),
        'omitted_finding_count': len(analysis.findings) - len(findings),
    }
    if analysis.analysis_id is not None:
        payload['analysis_id'] = analysis.analysis_id
    return payload


def coaching_manifest_fingerprint(manifest: dict) -> str:
    """Hash effective evidence while ignoring immutable database row identity."""
    key = 'analyses' if manifest.get('kind') == 'daily_review' else 'recent_analyses'
    effective = {**manifest, key: [
        {name: value for name, value in item.items() if name != 'analysis_id'}
        for item in manifest.get(key, ())
    ]}
    return canonical_fingerprint(effective)


def _session_payload(session: ActivitySession) -> dict:
    return {
        'id': session.id, 'date': session.local_date.isoformat(), 'status': session.status,
        'workout_id': session.workout_id, 'candidate_workout_ids': [w.id for w in session.candidates],
        'activities': [{
            'id': activity.id, 'started_at': utc(activity.started_at).isoformat(),
            'duration_seconds': activity.duration_seconds, 'distance_meters': activity.distance_meters,
            'average_heart_rate': activity.average_heart_rate,
            'matched_workout_id': activity.matched_workout_id,
        } for activity in session.activities],
    }


def _safe_baseline(profile: AthleteProfile | None) -> dict | None:
    if profile is None:
        return None
    return {
        'experience_level': profile.experience_level,
        'weekly_mileage_km': profile.current_weekly_mileage_km,
        'max_runs_per_week': profile.preferences.max_runs_per_week,
        'max_hard_sessions_per_week': profile.preferences.max_hard_sessions_per_week,
        'injury_status': profile.preferences.injury_status,
    }


def _health_rows(metrics: tuple[DailyHealthMetrics, ...], user_id: str,
                 starts_on: date, ends_on: date) -> list[dict]:
    return [{'date': m.metric_date.isoformat(), 'values': m.values_by_metric_type()}
            for m in sorted(metrics, key=lambda item: item.metric_date)
            if m.user_id == user_id and starts_on <= m.metric_date <= ends_on]


def _detail_refs(store: CoachingAnalysisEvidenceStore, user_id: str,
                 starts_on: date, ends_on: date, cutoff: datetime,
                 zone: ZoneInfo, allowed_ids: set[str] | None = None) -> list[dict]:
    rows = (store.list_current_detail_snapshots(user_id, starts_on, ends_on, cutoff)
            if hasattr(store, 'list_current_detail_snapshots') else ())
    return sorted(({
        'activity_id': row['activity_id'], 'resource': row['resource'],
        'snapshot_id': row['snapshot_id'],
        'activity_date': utc(row['started_at']).astimezone(zone).date().isoformat(),
    } for row in rows if row.get('snapshot_id') and
        (allowed_ids is None or row['activity_id'] in allowed_ids) and
        starts_on <= utc(row['started_at']).astimezone(zone).date() <= ends_on),
        key=lambda row: (row['activity_date'], row['activity_id'], row['resource']))


def build_coaching_evidence(*, user_id: str, kind: Literal['daily_review', 'workout_advice'],
                            local_date: date, timezone_name: str, workout_id: str | None,
                            constraints: WorkoutAdviceConstraints | None, as_of: datetime,
                            store: CoachingAnalysisEvidenceStore) -> CoachingEvidenceBundle:
    zone = ZoneInfo(timezone_name)
    cutoff = utc(as_of)
    if cutoff.astimezone(zone).date() < local_date:
        raise ValueError('local_date is after as_of in athlete timezone')
    if kind not in ('daily_review', 'workout_advice'):
        raise ValueError('unsupported coaching workflow')
    if kind == 'daily_review':
        review = store.load_review_evidence(user_id, local_date, timezone_name, cutoff)
        period = review.period
        starts, ends = period.starts_on, period.ends_on
        analyses = store.list_execution_analyses(user_id, starts, ends, cutoff)
        referenced = {a.id for s in review.sessions for a in s.activities}
        selected = tuple(a for a in analyses if set(a.activity_ids) & referenced and
                         (a.activity_started_at is None or starts <=
                          utc(a.activity_started_at).astimezone(zone).date() <= ends))
        metrics = store.list_recovery_metrics(user_id, starts, ends)
        missing_dates = [day.isoformat() for offset in range(7)
                         if (day := starts + timedelta(days=offset)) not in review.covered_dates]
        review_facts = {
            'prescriptions': bool(review.prescriptions),
            'sessions': bool(review.sessions),
            'execution_analyses': bool(selected),
            'complete_activity_coverage': not missing_dates,
        }
        manifest = {
            'schema_version': 'coaching-evidence-v1', 'kind': kind, 'user_id': user_id,
            'local_date': local_date.isoformat(), 'timezone_name': timezone_name,
            'periods': {'reviewed_date': period.reviewed_date.isoformat(),
                        'starts_on': starts.isoformat(), 'ends_on': ends.isoformat()},
            'prescriptions': [{'plan_id': p.plan_id, 'workout_id': p.workout_id,
                               'revision_id': p.revision_id, 'confidence': p.confidence,
                               'effective_at': utc(p.effective_at).isoformat(),
                               'workout': p.workout.to_payload()} for p in review.prescriptions],
            'sessions': [_session_payload(s) for s in review.sessions],
            'analyses': [_analysis_payload(a) for a in selected],
            'detail_snapshots': _detail_refs(store, user_id, starts, ends, cutoff, zone,
                                             referenced),
            'recovery_dates': _health_rows(metrics, user_id, starts, ends),
            'coverage': {'covered_dates': sorted(d.isoformat() for d in review.covered_dates
                                                  if starts <= d <= ends), 'missing_dates': missing_dates,
                         'uncertainty_reasons': list(review.uncertainty_reasons)},
            'action': {'state': 'review',
                       'available_facts': [name for name, present in review_facts.items() if present],
                       'missing_facts': [name for name, present in review_facts.items() if not present]},
        }
    else:
        context = store.load_advice_context(user_id, local_date, timezone_name, workout_id, cutoff)
        starts, ends = local_date - timedelta(days=28), local_date - timedelta(days=1)
        analyses = store.list_execution_analyses(user_id, starts, ends, cutoff)
        analyses = tuple(a for a in analyses if a.activity_started_at is None or
                         starts <= utc(a.activity_started_at).astimezone(zone).date() <= ends)
        selected = analyses[:7]
        metrics = store.list_recovery_metrics(user_id, ends, local_date)
        recovery = build_workout_recovery(user_id=user_id, advice_date=local_date,
                                          health_metrics=tuple(metrics))
        workout = context.workout
        state = ('no_plan' if context.plan is None else 'rest_day' if workout is None
                 else 'completed' if workout.status in ('completed', 'skipped') or any(
                     s.workout_id == workout.id and s.status in ('confirmed', 'automatic')
                     for s in context.today_sessions)
                 else 'needs_pairing' if any(s.status == 'needs_review'
                                             for s in context.today_sessions) else 'planned')
        action_facts = {
            'workout': bool(workout),
            'activity_sync': context.activity_sync_usable,
            'athlete_baseline': bool(context.athlete_baseline),
            'today_recovery_signals': bool(recovery['days'][-1]['signals']),
            'today_readiness': recovery['observed_date'] == local_date.isoformat()
                               and recovery['readiness_label'] != 'unknown',
            'previous_day_recovery': bool(recovery['days'][0]['signals']),
        }
        manifest = {
            'schema_version': 'coaching-evidence-v1', 'kind': kind, 'user_id': user_id,
            'local_date': local_date.isoformat(), 'timezone_name': timezone_name,
            'periods': {'today': local_date.isoformat(), 'history_starts_on': starts.isoformat(),
                        'history_ends_on': ends.isoformat(),
                        'next_through': (local_date + timedelta(days=7)).isoformat()},
            'plan': {'id': context.plan.id, 'starts_on': context.plan.starts_on.isoformat(),
                     'ends_on': context.plan.ends_on.isoformat()} if context.plan else None,
            'workout': workout.to_payload() if workout else None,
            'today_sessions': [_session_payload(s) for s in context.today_sessions],
            'activity_sync_usable': context.activity_sync_usable,
            'athlete_baseline': _safe_baseline(context.athlete_baseline),
            'next_workouts': [w.to_payload() for w in context.next_workouts[:2]],
            'recent_analyses': [_analysis_payload(a) for a in selected],
            'detail_snapshots': _detail_refs(store, user_id, starts, local_date, cutoff, zone),
            'history_counts': {'analysed_activities': len(analyses),
                               'uncertain_analyses': sum(bool(a.limitations) for a in analyses),
                               'by_mapping': dict(sorted(Counter(a.mapping for a in analyses).items())),
                               'by_finding': dict(sorted(Counter(f.code for a in analyses
                                                                 for f in a.findings).items()))},
            'recovery': recovery,
            'constraints': {'available_minutes': constraints.available_minutes,
                            'feeling': constraints.feeling,
                            'cannot_train_today': constraints.cannot_train_today} if constraints else None,
            'action': {'state': state,
                       'available_facts': [name for name, present in action_facts.items() if present],
                       'missing_facts': [name for name, present in action_facts.items() if not present]},
        }
    return CoachingEvidenceBundle(kind, local_date, timezone_name,
                                  coaching_manifest_fingerprint(manifest), manifest)
