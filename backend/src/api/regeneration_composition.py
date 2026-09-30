from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.api.dependencies import SessionDependency
from src.application.async_agent_runs import QueueAgentRunHandler
from src.application.training_plan_regeneration import (
    GetRegenerationOptionsHandler,
    StartRegenerationHandler,
)
from src.infrastructure.database.agent_run_repository import SqlAlchemyAgentRunRepository
from src.infrastructure.database.agent_task_queue import SqlAlchemyAgentTaskQueue
from src.infrastructure.database.athlete_race_repository import SqlAlchemyAthleteRaceRepository
from src.infrastructure.database.models import UserModel
from src.infrastructure.database.training_plan_repository import SqlAlchemyTrainingPlanRepository


def get_regeneration_options_handler(session: SessionDependency) -> GetRegenerationOptionsHandler:
    athlete_races = SqlAlchemyAthleteRaceRepository(session)
    return GetRegenerationOptionsHandler(
        profiles=athlete_races,
        race_goals=athlete_races,
        training_plans=SqlAlchemyTrainingPlanRepository(session),
        runs=SqlAlchemyAgentRunRepository(session),
    )


def _lock_user(session: Session, user_id: str) -> None:
    session.scalar(select(UserModel).where(UserModel.id == user_id).with_for_update())


def get_start_regeneration_handler(session: SessionDependency) -> StartRegenerationHandler:
    athlete_races = SqlAlchemyAthleteRaceRepository(session)
    runs = SqlAlchemyAgentRunRepository(session)
    tasks = SqlAlchemyAgentTaskQueue(session)
    return StartRegenerationHandler(
        profiles=athlete_races,
        race_goals=athlete_races,
        runs=runs,
        queue_agent_runs=QueueAgentRunHandler(
            runs=runs,
            queue=tasks,
            prompt_version="running-companion-v1",
            provider="local",
            model="deterministic-local-companion",
        ),
        lock_user=lambda user_id: _lock_user(session, user_id),
    )


RegenerationOptionsHandlerDependency = Annotated[
    GetRegenerationOptionsHandler, Depends(get_regeneration_options_handler)
]
StartRegenerationHandlerDependency = Annotated[
    StartRegenerationHandler, Depends(get_start_regeneration_handler)
]
