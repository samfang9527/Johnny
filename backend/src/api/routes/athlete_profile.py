from __future__ import annotations

from fastapi import APIRouter, HTTPException

from src.api.dependencies import CurrentUserDependency, SessionDependency, ensure_current_user
from src.api.errors import ApiNotFoundError
from src.api.schemas.athlete_profile import AthleteProfileRequest, AthleteProfileResponse
from src.api.schemas.common import DataEnvelope
from src.domain.athlete_race import AthleteProfile
from src.infrastructure.database.athlete_race_repository import SqlAlchemyAthleteRaceRepository


router = APIRouter(prefix="/athlete/profile", tags=["athlete-profile"])


@router.get("", response_model=DataEnvelope[AthleteProfileResponse])
def get_profile(
    current_user: CurrentUserDependency,
    session: SessionDependency,
) -> DataEnvelope[AthleteProfileResponse]:
    profile = SqlAlchemyAthleteRaceRepository(session).get_profile_for_user(current_user.id)
    if profile is None:
        raise ApiNotFoundError("athlete profile not found")
    return DataEnvelope(data=_profile_response(profile))


@router.put("", response_model=DataEnvelope[AthleteProfileResponse])
def save_profile(
    payload: AthleteProfileRequest,
    current_user: CurrentUserDependency,
    session: SessionDependency,
) -> DataEnvelope[AthleteProfileResponse]:
    repository = SqlAlchemyAthleteRaceRepository(session)
    existing = repository.get_profile_for_user(current_user.id)
    training_preferences = dict(existing.preferences.training_preferences) if existing is not None else {}
    if "training_preferences" in payload.model_fields_set:
        training_preferences.update(payload.training_preferences)
    if "threshold_pace_seconds_per_km" in payload.model_fields_set:
        if payload.threshold_pace_seconds_per_km is None:
            training_preferences.pop("threshold_pace_seconds_per_km", None)
        else:
            training_preferences["threshold_pace_seconds_per_km"] = payload.threshold_pace_seconds_per_km
    for field_name in ("resting_heart_rate_bpm", "max_heart_rate_bpm"):
        if field_name in payload.model_fields_set:
            value = getattr(payload, field_name)
            if value is None:
                training_preferences.pop(field_name, None)
            else:
                training_preferences[field_name] = value
    resting_hr = _heart_rate_setting(training_preferences, "resting_heart_rate_bpm")
    max_hr = _heart_rate_setting(training_preferences, "max_heart_rate_bpm")
    if resting_hr is not None and max_hr is not None and max_hr <= resting_hr:
        raise HTTPException(status_code=422, detail="maximum heart rate must exceed resting heart rate")

    profile = AthleteProfile.create(
        user_id=current_user.id,
        timezone=payload.timezone,
        experience_level=payload.experience_level,
        current_weekly_mileage_km=payload.current_weekly_mileage_km,
        preferred_training_days=tuple(payload.preferred_training_days),
        preferred_long_run_day=payload.preferred_long_run_day,
        max_runs_per_week=payload.max_runs_per_week,
        max_hard_sessions_per_week=payload.max_hard_sessions_per_week,
        unit_preference=payload.unit_preference,
        training_preferences=training_preferences,
        injury_status=payload.injury_status,
        injury_areas=tuple(payload.injury_areas),
        injury_notes=payload.injury_notes,
    )
    ensure_current_user(session, current_user)
    saved = repository.save_profile(current_user.id, profile)
    return DataEnvelope(data=_profile_response(saved))


def _profile_response(profile: AthleteProfile) -> AthleteProfileResponse:
    threshold_pace = profile.preferences.training_preferences.get("threshold_pace_seconds_per_km")
    if not isinstance(threshold_pace, int) or isinstance(threshold_pace, bool) or not 120 <= threshold_pace <= 900:
        threshold_pace = None
    return AthleteProfileResponse(
        id=profile.id,
        user_id=profile.user_id,
        timezone=profile.timezone,
        experience_level=profile.experience_level,
        current_weekly_mileage_km=profile.current_weekly_mileage_km,
        preferred_training_days=list(profile.preferences.preferred_training_days),
        preferred_long_run_day=profile.preferences.preferred_long_run_day,
        max_runs_per_week=profile.preferences.max_runs_per_week,
        max_hard_sessions_per_week=profile.preferences.max_hard_sessions_per_week,
        unit_preference=profile.preferences.unit_preference,
        threshold_pace_seconds_per_km=threshold_pace,
        resting_heart_rate_bpm=_heart_rate_setting(profile.preferences.training_preferences, "resting_heart_rate_bpm"),
        max_heart_rate_bpm=_heart_rate_setting(profile.preferences.training_preferences, "max_heart_rate_bpm"),
        training_preferences={key: value for key, value in profile.preferences.training_preferences.items() if key != "garmin_training_evidence"},
        garmin_training_evidence=profile.preferences.training_preferences.get("garmin_training_evidence", {}),
        injury_status=profile.preferences.injury_status,
        injury_areas=list(profile.preferences.injury_areas),
        injury_notes=profile.preferences.injury_notes,
    )


def _heart_rate_setting(training_preferences: dict, name: str) -> int | None:
    value = training_preferences.get(name)
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else None
