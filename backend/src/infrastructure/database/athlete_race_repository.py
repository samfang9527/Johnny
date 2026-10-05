from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.domain.athlete_race import AthletePreferences, AthleteProfile, RaceGoal

from .models import AthleteProfileModel, RaceModel


class SqlAlchemyAthleteRaceRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def save_profile(self, user_id: str, profile: AthleteProfile) -> AthleteProfile:
        _ensure_matching_user_id(user_id, profile.user_id)
        model = self._get_profile_model(user_id, profile)
        model.user_id = user_id
        model.timezone = profile.timezone
        model.experience_level = profile.experience_level
        model.metadata_json = _profile_metadata(profile)
        self._session.flush()
        return _profile_from_model(model)

    def get_profile_for_user(self, user_id: str) -> AthleteProfile | None:
        model = self._session.scalar(select(AthleteProfileModel).where(AthleteProfileModel.user_id == user_id))
        if model is None:
            return None
        return _profile_from_model(model)

    def list_profiles_for_users(self, user_ids: list[str]) -> list[AthleteProfile]:
        if not user_ids:
            return []
        statement = (
            select(AthleteProfileModel)
            .where(AthleteProfileModel.user_id.in_(user_ids))
            .order_by(AthleteProfileModel.user_id)
        )
        return [_profile_from_model(model) for model in self._session.scalars(statement)]

    def create_race_goal(self, user_id: str, race_goal: RaceGoal) -> RaceGoal:
        _ensure_matching_user_id(user_id, race_goal.user_id)
        model = RaceModel(
            user_id=user_id,
            name=race_goal.name,
            race_date=race_goal.race_date,
            distance_meters=race_goal.distance_meters,
            status=race_goal.status,
            metadata_json=_race_metadata(race_goal),
        )
        self._session.add(model)
        self._session.flush()
        return _race_goal_from_model(model)

    def list_race_goals_for_user(
        self,
        user_id: str,
        *,
        race_date_from: date | None = None,
        race_date_to: date | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[RaceGoal]:
        if limit is not None and limit < 0:
            raise ValueError("limit must be non-negative")
        if offset < 0:
            raise ValueError("offset must be non-negative")

        statement = select(RaceModel).where(RaceModel.user_id == user_id)
        if race_date_from is not None:
            statement = statement.where(RaceModel.race_date >= race_date_from)
        if race_date_to is not None:
            statement = statement.where(RaceModel.race_date <= race_date_to)
        statement = statement.order_by(RaceModel.race_date, RaceModel.id).offset(offset)
        if limit is not None:
            statement = statement.limit(limit)
        return [_race_goal_from_model(model) for model in self._session.scalars(statement)]

    def get_race_goal_for_user(self, user_id: str, race_goal_id: str | None) -> RaceGoal | None:
        if race_goal_id is None:
            return None
        model = self._session.scalar(
            select(RaceModel).where(
                RaceModel.id == race_goal_id,
                RaceModel.user_id == user_id,
            )
        )
        if model is None:
            return None
        return _race_goal_from_model(model)

    def list_race_goals_for_users(
        self,
        user_ids: list[str],
        *,
        race_date_from: date | None = None,
        statuses: tuple[str, ...] | None = None,
    ) -> list[RaceGoal]:
        if not user_ids:
            return []
        statement = select(RaceModel).where(RaceModel.user_id.in_(user_ids))
        if race_date_from is not None:
            statement = statement.where(RaceModel.race_date >= race_date_from)
        if statuses is not None:
            statement = statement.where(RaceModel.status.in_(statuses))
        statement = statement.order_by(RaceModel.user_id, RaceModel.race_date, RaceModel.id)
        return [_race_goal_from_model(model) for model in self._session.scalars(statement)]

    def update_race_goal(self, user_id: str, race_goal: RaceGoal) -> RaceGoal | None:
        _ensure_matching_user_id(user_id, race_goal.user_id)
        if race_goal.id is None:
            raise ValueError("Race goal id is required for update")
        model = self._session.scalar(
            select(RaceModel).where(
                RaceModel.id == race_goal.id,
                RaceModel.user_id == user_id,
            )
        )
        if model is None:
            return None
        model.name = race_goal.name
        model.race_date = race_goal.race_date
        model.distance_meters = race_goal.distance_meters
        model.status = race_goal.status
        model.metadata_json = _race_metadata(race_goal)
        self._session.flush()
        return _race_goal_from_model(model)

    def delete_race_goal(self, user_id: str, race_goal_id: str) -> bool:
        model = self._session.scalar(
            select(RaceModel).where(RaceModel.id == race_goal_id, RaceModel.user_id == user_id)
        )
        if model is None:
            return False
        # Detach the target, retaining every plan version and its workouts.
        for plan in list(model.training_plans):
            plan.race = None
        self._session.delete(model)
        self._session.flush()
        return True

    def _get_profile_model(self, user_id: str, profile: AthleteProfile) -> AthleteProfileModel:
        if profile.id is not None:
            existing = self._session.scalar(
                select(AthleteProfileModel).where(
                    AthleteProfileModel.id == profile.id,
                    AthleteProfileModel.user_id == user_id,
                )
            )
            if existing is not None:
                return existing

        existing_for_user = self._session.scalar(
            select(AthleteProfileModel).where(AthleteProfileModel.user_id == user_id)
        )
        if existing_for_user is not None:
            return existing_for_user

        model = AthleteProfileModel(user_id=user_id)
        self._session.add(model)
        return model


def _ensure_matching_user_id(trusted_user_id: str, payload_user_id: str) -> None:
    if trusted_user_id != payload_user_id:
        raise ValueError("payload user_id does not match repository user_id")


def _profile_metadata(profile: AthleteProfile) -> dict:
    return {
        "current_weekly_mileage_km": profile.current_weekly_mileage_km,
        "preferred_training_days": list(profile.preferences.preferred_training_days),
        "preferred_long_run_day": profile.preferences.preferred_long_run_day,
        "max_runs_per_week": profile.preferences.max_runs_per_week,
        "max_hard_sessions_per_week": profile.preferences.max_hard_sessions_per_week,
        "unit_preference": profile.preferences.unit_preference,
        "training_preferences": profile.preferences.training_preferences,
        "injury_status": profile.preferences.injury_status,
        "injury_areas": list(profile.preferences.injury_areas),
        "injury_notes": profile.preferences.injury_notes,
    }


def _profile_from_model(model: AthleteProfileModel) -> AthleteProfile:
    metadata = model.metadata_json or {}
    experience_level = None if model.experience_level == "unknown" else model.experience_level
    return AthleteProfile(
        id=model.id,
        user_id=model.user_id,
        timezone=model.timezone,
        experience_level=experience_level,
        current_weekly_mileage_km=float(metadata.get("current_weekly_mileage_km", metadata.get("current_weekly_mileage", 0))),
        preferences=AthletePreferences(
            preferred_training_days=tuple(metadata.get("preferred_training_days", ())),
            preferred_long_run_day=metadata.get("preferred_long_run_day", "sunday"),
            max_runs_per_week=int(metadata.get("max_runs_per_week", 1)),
            max_hard_sessions_per_week=int(metadata.get("max_hard_sessions_per_week", 2)),
            unit_preference=metadata.get("unit_preference", "metric"),
            training_preferences=metadata.get("training_preferences", {}),
            injury_status=metadata.get("injury_status", "none"),
            injury_areas=tuple(metadata.get("injury_areas", ())),
            injury_notes=metadata.get("injury_notes"),
        ),
    )


def _race_metadata(race_goal: RaceGoal) -> dict:
    return {
        "target_finish_seconds": race_goal.target_finish_seconds,
        "ascent_meters": race_goal.ascent_meters,
        "descent_meters": race_goal.descent_meters,
        "terrain_difficulty": race_goal.terrain_difficulty,
        "cutoff_seconds": race_goal.cutoff_seconds,
        "goal_intent": race_goal.goal_intent,
        "priority": race_goal.priority,
        "target_pace_seconds_per_km": race_goal.target_pace_seconds_per_km,
    }


def _race_goal_from_model(model: RaceModel) -> RaceGoal:
    metadata = model.metadata_json or {}
    return RaceGoal(
        id=model.id,
        user_id=model.user_id,
        name=model.name,
        race_date=model.race_date,
        distance_meters=model.distance_meters,
        target_finish_seconds=metadata.get("target_finish_seconds"),
        ascent_meters=metadata.get("ascent_meters"),
        descent_meters=metadata.get("descent_meters"),
        terrain_difficulty=metadata.get("terrain_difficulty"),
        cutoff_seconds=metadata.get("cutoff_seconds"),
        goal_intent=metadata.get("goal_intent"),
        priority=metadata.get("priority", "primary"),
        status=model.status,
    )
