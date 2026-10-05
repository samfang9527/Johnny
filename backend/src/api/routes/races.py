from __future__ import annotations

from datetime import date

from fastapi import APIRouter

from src.api.dependencies import CurrentUserDependency, SessionDependency, ensure_current_user
from src.api.errors import ApiNotFoundError
from src.api.schemas.common import DEFAULT_PAGE_LIMIT, DataEnvelope, ListEnvelope, PageLimit, PageOffset, list_envelope, page_query_limit
from src.api.schemas.races import RaceGoalCreateRequest, RaceGoalResponse, RaceGoalUpdateRequest
from src.domain.athlete_race import RaceGoal
from src.infrastructure.database.athlete_race_repository import SqlAlchemyAthleteRaceRepository


router = APIRouter(prefix="/races", tags=["races"])


@router.post("")
def create_race_goal(
    payload: RaceGoalCreateRequest,
    current_user: CurrentUserDependency,
    session: SessionDependency,
) -> DataEnvelope[RaceGoalResponse]:
    repository = SqlAlchemyAthleteRaceRepository(session)
    race = RaceGoal.create(user_id=current_user.id, **payload.model_dump())
    ensure_current_user(session, current_user)
    return DataEnvelope(data=_race_response(repository.create_race_goal(current_user.id, race)))


@router.get("")
def list_race_goals(
    current_user: CurrentUserDependency,
    session: SessionDependency,
    race_date_from: date | None = None,
    race_date_to: date | None = None,
    limit: PageLimit = DEFAULT_PAGE_LIMIT,
    offset: PageOffset = 0,
) -> ListEnvelope[RaceGoalResponse]:
    races = SqlAlchemyAthleteRaceRepository(session).list_race_goals_for_user(
        current_user.id,
        race_date_from=race_date_from,
        race_date_to=race_date_to,
        limit=page_query_limit(limit),
        offset=offset,
    )
    return list_envelope([_race_response(race) for race in races], limit=limit, offset=offset)


@router.get("/{race_id}", response_model=DataEnvelope[RaceGoalResponse])
def get_race_goal(
    race_id: str,
    current_user: CurrentUserDependency,
    session: SessionDependency,
) -> DataEnvelope[RaceGoalResponse]:
    race = SqlAlchemyAthleteRaceRepository(session).get_race_goal_for_user(current_user.id, race_id)
    if race is None:
        raise ApiNotFoundError("race goal not found")
    return DataEnvelope(data=_race_response(race))


@router.put("/{race_id}", response_model=DataEnvelope[RaceGoalResponse])
def update_race_goal(
    race_id: str,
    payload: RaceGoalUpdateRequest,
    current_user: CurrentUserDependency,
    session: SessionDependency,
) -> DataEnvelope[RaceGoalResponse]:
    repository = SqlAlchemyAthleteRaceRepository(session)
    race = RaceGoal.create(id=race_id, user_id=current_user.id, **payload.model_dump())
    saved = repository.update_race_goal(current_user.id, race)
    if saved is None:
        raise ApiNotFoundError("race goal not found")
    return DataEnvelope(data=_race_response(saved))


@router.delete("/{race_id}")
def delete_race_goal(
    race_id: str,
    current_user: CurrentUserDependency,
    session: SessionDependency,
) -> DataEnvelope[dict[str, str]]:
    if not SqlAlchemyAthleteRaceRepository(session).delete_race_goal(current_user.id, race_id):
        raise ApiNotFoundError("race goal not found")
    return DataEnvelope(data={"id": race_id})


def _race_response(race: RaceGoal) -> RaceGoalResponse:
    return RaceGoalResponse(
        id=race.id,
        user_id=race.user_id,
        name=race.name,
        race_date=race.race_date,
        distance_meters=race.distance_meters,
        target_finish_seconds=race.target_finish_seconds,
        ascent_meters=race.ascent_meters,
        descent_meters=race.descent_meters,
        terrain_difficulty=race.terrain_difficulty,
        cutoff_seconds=race.cutoff_seconds,
        goal_intent=race.goal_intent,
        priority=race.priority,
        status=race.status,
        target_pace_seconds_per_km=race.target_pace_seconds_per_km,
    )
