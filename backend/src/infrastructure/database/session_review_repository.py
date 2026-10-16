"""Owner-scoped review decisions stored alongside immutable activity recordings."""
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
from .models import ActivityModel


class SessionReviewConflict(ValueError):
    pass


REVIEW_WINDOW_DAYS = 8


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
        activities = tuple(a for a in self.activities.list_activities_for_user_between(user_id, start-timedelta(days=1), end+timedelta(days=1))
                           if start <= utc(a.started_at).astimezone(zone).date() <= end)
        workouts = []
        for day in sorted({utc(a.started_at).astimezone(zone).date() for a in activities}):
            plan = resolve_plan_for_date(self.plans, user_id, day)
            if plan:
                workouts.extend(w for w in plan.workouts if w.scheduled_for == day)
        return match_sessions(activities, tuple(workouts), name)

    def save_decisions(self, user_id: str, activity_ids: list[str], groups: list[dict]) -> date:
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
            raise SessionReviewConflict('activity pairing can only be changed within the latest eight local dates')
        sessions = self.list_sessions(user_id, day, day)
        selected = set(activity_ids)
        for candidate in sessions:
            candidate_ids = {a.id for a in candidate.activities}
            if candidate_ids & selected and not candidate_ids <= selected:
                raise SessionReviewConflict('recordings changed; reload the complete session before saving')
        valid_workouts = {w.id for s in sessions for w in s.candidates}
        by_id = {m.id: m for m in models}
        for group in groups:
            if group['workout_id'] is not None and group['workout_id'] not in valid_workouts:
                raise LookupError('workout not found for this activity date')
            ordered = sorted((by_id[aid] for aid in group['activity_ids']), key=lambda m: utc(m.started_at))
            for first, second in zip(ordered, ordered[1:]):
                gap = utc(second.started_at) - utc(first.started_at) - timedelta(seconds=first.duration_seconds or 0)
                if not timedelta(0) <= gap <= timedelta(minutes=30):
                    raise DomainValidationError('group recordings must not overlap or have gaps longer than 30 minutes')
        for group in groups:
            group_id = str(uuid4())
            for aid in group['activity_ids']:
                model = by_id[aid]
                model.provider_summary = {**(model.provider_summary or {}), 'session_group_id': group_id,
                    'match_reviewed': True, 'matched_workout_id': group['workout_id']}
        self.session.flush()
        return day


def session_payload(item):
    return {
        'id': item.id, 'local_date': item.local_date.isoformat(), 'status': item.status,
        'workout_id': item.workout_id, 'duration_seconds': item.duration_seconds, 'distance_meters': item.distance_meters,
        'activities': [{'id': a.id, 'started_at': utc(a.started_at).isoformat(), 'sport_type': a.sport_type,
                        'duration_seconds': a.duration_seconds, 'distance_meters': a.distance_meters} for a in item.activities],
        'candidates': [{'id': w.id, 'scheduled_for': w.scheduled_for.isoformat(), 'workout_type': w.workout_type,
                        'purpose': w.purpose} for w in item.candidates],
    }
