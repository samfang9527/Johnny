from __future__ import annotations

from fastapi import APIRouter

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
    profile = AthleteProfile.create(
        user_id=current_user.id,
        timezone=payload.timezone,
        experience_level=payload.experience_level,
        current_weekly_mileage=payload.current_weekly_mileage,
        preferred_training_days=tuple(payload.preferred_training_days),
        preferred_long_run_day=payload.preferred_long_run_day,
        max_runs_per_week=payload.max_runs_per_week,
        unit_preference=payload.unit_preference,
        training_preferences=payload.training_preferences,
        injury_notes=payload.injury_notes,
    )
    ensure_current_user(session, current_user)
    saved = SqlAlchemyAthleteRaceRepository(session).save_profile(current_user.id, profile)
    return DataEnvelope(data=_profile_response(saved))


def _profile_response(profile: AthleteProfile) -> AthleteProfileResponse:
    return AthleteProfileResponse(
        id=profile.id,
        user_id=profile.user_id,
        timezone=profile.timezone,
        experience_level=profile.experience_level,
        current_weekly_mileage=profile.current_weekly_mileage,
        preferred_training_days=list(profile.preferences.preferred_training_days),
        preferred_long_run_day=profile.preferences.preferred_long_run_day,
        max_runs_per_week=profile.preferences.max_runs_per_week,
        unit_preference=profile.preferences.unit_preference,
        training_preferences=profile.preferences.training_preferences,
        injury_notes=profile.preferences.injury_notes,
    )
