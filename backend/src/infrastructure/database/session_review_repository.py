"""Owner-scoped review decisions stored alongside immutable activity recordings."""
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from uuid import uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.application.training_analytics import resolve_plan_for_date
from src.domain.activity_health import DomainValidationError
from src.domain.activity_sessions import match_sessions, utc
from src.domain.running import is_running
from .activity_repository import SqlAlchemyActivityRepository
from .athlete_race_repository import SqlAlchemyAthleteRaceRepository
from .training_plan_repository import SqlAlchemyTrainingPlanRepository
from .models import ActivityModel, TrainingPlanModel, WorkoutModel


class SessionReviewConflict(ValueError):
    pass


REVIEW_WINDOW_DAYS = 7


class SqlAlchemySessionReviewRepository:
    def __init__(self, session: Session):
        self.session = session
        self.activities = SqlAlchemyActivityRepository(session)
        self.plans = SqlAlchemyTrainingPlanRepository(session)

    def timezone_for(self, user_id: str) -> str:
        profile = SqlAlchemyAthleteRaceRepository(self.session).get_profile_for_user(user_id)
        name = profile.timezone if profile else 'UTC'
        try:
            ZoneInfo(name)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise SessionReviewConflict('athlete timezone is invalid') from exc
        return name

    def review_window(self, user_id: str) -> tuple[date, date]:
        today = datetime.now(timezone.utc).astimezone(ZoneInfo(self.timezone_for(user_id))).date()
        return today - timedelta(days=REVIEW_WINDOW_DAYS - 1), today

    def list_sessions(self, user_id: str, start: date, end: date):
        name = self.timezone_for(user_id)
        zone = ZoneInfo(name)
        # Include neighboring sessions so an already claimed workout is not
        # automatically offered again on its scheduled date.
        activities = tuple(a for a in self.activities.list_activities_for_user_between(user_id, start-timedelta(days=2), end+timedelta(days=2))
                           if start-timedelta(days=1) <= utc(a.started_at).astimezone(zone).date() <= end+timedelta(days=1))
        workouts = []
        activity_days = {utc(a.started_at).astimezone(zone).date() for a in activities}
        workout_days = {day + timedelta(days=offset) for day in activity_days for offset in (-1, 0, 1)}
        for day in sorted(workout_days):
            plan = resolve_plan_for_date(self.plans, user_id, day)
            if plan:
                workouts.extend(w for w in plan.workouts if w.scheduled_for == day)
        sessions = match_sessions(activities, tuple(workouts), name)
        workouts_by_id = {workout.id: workout for workout in workouts}
        first_day, last_day = self.review_window(user_id)
        with_swaps = []
        for current in sessions:
            source = workouts_by_id.get(current.workout_id)
            swaps = ()
            if source and source.workout_type != 'race':
                swaps = tuple((target, other.local_date) for other in sessions if other is not current
                              and other.workout_id != current.workout_id
                              and abs((other.local_date - current.local_date).days) == 1
                              and first_day <= other.local_date <= last_day
                              and abs((source.scheduled_for - other.local_date).days) <= 1
                              and (target := workouts_by_id.get(other.workout_id)) is not None
                              and abs((target.scheduled_for - current.local_date).days) <= 1
                              and target.workout_type != 'race')
            with_swaps.append(replace(current, swap_candidates=swaps))
        return tuple(s for s in with_swaps if start <= s.local_date <= end)

    def swap_decisions(self, user_id: str, activity_ids: list[str], workout_id: str) -> set[date]:
        if not activity_ids or len(activity_ids) != len(set(activity_ids)):
            raise DomainValidationError('swap requires one complete activity session')
        selected = list(self.session.scalars(select(ActivityModel).where(
            ActivityModel.user_id == user_id, ActivityModel.id.in_(activity_ids)
        )))
        if len(selected) != len(activity_ids):
            raise LookupError('activity not found')
        zone = ZoneInfo(self.timezone_for(user_id))
        dates = {utc(model.started_at).astimezone(zone).date() for model in selected}
        if len(dates) != 1 or any(not is_running(model.activity_type) for model in selected):
            raise SessionReviewConflict('swap requires one local-day running session')
        day = next(iter(dates))
        first_day, last_day = self.review_window(user_id)
        if not first_day <= day <= last_day:
            raise SessionReviewConflict('activity pairing can only be changed within the latest seven local dates')

        def find_pair():
            sessions = self.list_sessions(user_id, day-timedelta(days=1), day+timedelta(days=1))
            source = next((item for item in sessions
                           if {activity.id for activity in item.activities} == set(activity_ids)), None)
            target = next((item for item in sessions if item.workout_id == workout_id
                           and item is not source), None)
            if (source is None or target is None or source.workout_id is None
                    or workout_id not in {workout.id for workout, _ in source.swap_candidates}
                    or not first_day <= target.local_date <= last_day):
                raise SessionReviewConflict('these sessions cannot exchange workouts; reload and review both dates')
            return source, target

        source, target = find_pair()
        involved_ids = sorted({activity.id for item in (source, target) for activity in item.activities})
        models = list(self.session.scalars(select(ActivityModel).where(
            ActivityModel.user_id == user_id, ActivityModel.id.in_(involved_ids)
        ).order_by(ActivityModel.id).with_for_update().execution_options(populate_existing=True)))
        if len(models) != len(involved_ids):
            raise SessionReviewConflict('recordings changed; reload before swapping')
        self.session.scalars(select(WorkoutModel.id).join(TrainingPlanModel).where(
            TrainingPlanModel.user_id == user_id,
            WorkoutModel.id.in_((source.workout_id, workout_id)),
        ).order_by(WorkoutModel.id).with_for_update(of=WorkoutModel)).all()
        self.session.expire_all()
        source, target = find_pair()
        if {activity.id for item in (source, target) for activity in item.activities} != set(involved_ids):
            raise SessionReviewConflict('recordings changed; reload before swapping')
        by_id = {model.id: model for model in models}
        for item, replacement in ((source, workout_id), (target, source.workout_id)):
            group_id = str(uuid4())
            for activity in item.activities:
                model = by_id[activity.id]
                model.provider_summary = {**(model.provider_summary or {}),
                    'session_group_id': group_id, 'match_reviewed': True,
                    'matched_workout_id': replacement}
        self.session.flush()
        return {source.local_date, target.local_date}

    def save_decisions(self, user_id: str, activity_ids: list[str], groups: list[dict]) -> set[date]:
        members = [aid for group in groups for aid in group['activity_ids']]
        if (not activity_ids or len(set(activity_ids)) != len(activity_ids) or len(set(members)) != len(members)
                or set(members) != set(activity_ids) or any(not g['activity_ids'] for g in groups)):
            raise DomainValidationError('groups must partition every selected recording exactly once')
        # Row locks serialize competing decisions without changing imported activity fields.
        models = list(self.session.scalars(select(ActivityModel).where(
            ActivityModel.user_id == user_id, ActivityModel.id.in_(activity_ids)
        ).order_by(ActivityModel.id).with_for_update()))
        if len(models) != len(activity_ids):
            raise LookupError('activity not found')
        zone = ZoneInfo(self.timezone_for(user_id))
        dates = {utc(m.started_at).astimezone(zone).date() for m in models}
        if len(dates) != 1 or any(not is_running(m.activity_type) for m in models):
            raise DomainValidationError('review recordings must be running activities on one local day')
        day = next(iter(dates))
        first_day, last_day = self.review_window(user_id)
        if not first_day <= day <= last_day:
            raise SessionReviewConflict('activity pairing can only be changed within the latest seven local dates')
        requested = [group['workout_id'] for group in groups if group['workout_id'] is not None]
        if len(requested) != len(set(requested)):
            raise SessionReviewConflict('one workout cannot be paired with multiple sessions')
        # Serialize claims from distinct sessions before reading existing matches.
        if requested:
            self.session.scalars(select(WorkoutModel.id).join(TrainingPlanModel).where(
                TrainingPlanModel.user_id == user_id, WorkoutModel.id.in_(requested)
            ).order_by(WorkoutModel.id).with_for_update(of=WorkoutModel)).all()
        sessions = self.list_sessions(user_id, day-timedelta(days=1), day+timedelta(days=1))
        selected = set(activity_ids)
        for candidate in sessions:
            candidate_ids = {a.id for a in candidate.activities}
            if candidate_ids & selected and not candidate_ids <= selected:
                raise SessionReviewConflict('recordings changed; reload the complete session before saving')
        valid_workouts = {w.id: w for s in sessions if s.local_date == day for w in s.candidates}
        for session in sessions:
            if session.workout_id in requested and not {a.id for a in session.activities} <= selected:
                raise SessionReviewConflict('workout is already paired with another session')
        by_id = {m.id: m for m in models}
        for group in groups:
            if group['workout_id'] is not None and group['workout_id'] not in valid_workouts:
                raise LookupError('workout not found within one day of this activity')
            ordered = sorted((by_id[aid] for aid in group['activity_ids']), key=lambda m: utc(m.started_at))
            for first, second in zip(ordered, ordered[1:]):
                gap = utc(second.started_at) - utc(first.started_at) - timedelta(seconds=first.duration_seconds or 0)
                if not timedelta(0) <= gap <= timedelta(minutes=30):
                    raise DomainValidationError('group recordings must not overlap or have gaps longer than 30 minutes')
        changed_dates = {day}
        for model in models:
            previous = (model.provider_summary or {}).get('matched_workout_id')
            if previous in valid_workouts:
                changed_dates.add(valid_workouts[previous].scheduled_for)
        changed_dates.update(valid_workouts[workout_id].scheduled_for for workout_id in requested)
        for group in groups:
            group_id = str(uuid4())
            for aid in group['activity_ids']:
                model = by_id[aid]
                model.provider_summary = {**(model.provider_summary or {}), 'session_group_id': group_id,
                    'match_reviewed': True, 'matched_workout_id': group['workout_id']}
        self.session.flush()
        return changed_dates


def session_payload(item):
    return {
        'id': item.id, 'local_date': item.local_date.isoformat(), 'status': item.status,
        'workout_id': item.workout_id, 'duration_seconds': item.duration_seconds, 'distance_meters': item.distance_meters,
        'activities': [{'id': a.id, 'started_at': utc(a.started_at).isoformat(), 'sport_type': a.sport_type,
                        'duration_seconds': a.duration_seconds, 'distance_meters': a.distance_meters} for a in item.activities],
        'candidates': [{'id': w.id, 'scheduled_for': w.scheduled_for.isoformat(), 'workout_type': w.workout_type,
                        'purpose': w.purpose} for w in item.candidates],
        'swap_candidates': [{'id': w.id, 'scheduled_for': w.scheduled_for.isoformat(), 'workout_type': w.workout_type,
                             'purpose': w.purpose, 'activity_date': activity_date.isoformat()}
                            for w, activity_date in item.swap_candidates],
    }
