from __future__ import annotations

import os
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
from src.domain.training_plan_regeneration import MANUAL_REGENERATION_LIMIT
from src.infrastructure.database.agent_run_repository import SqlAlchemyAgentRunRepository
from src.infrastructure.database.agent_task_queue import SqlAlchemyAgentTaskQueue
from src.infrastructure.database.athlete_race_repository import SqlAlchemyAthleteRaceRepository
from src.infrastructure.database.models import UserModel
from src.infrastructure.database.training_plan_repository import SqlAlchemyTrainingPlanRepository
from src.infrastructure.llm.settings import resolve_queued_training_plan_provider


def _manual_regeneration_limit() -> int:
    if os.getenv("ENV", "").strip().lower() not in {"local", "development"}:
        return MANUAL_REGENERATION_LIMIT
    configured = os.getenv("JOHNNY_DEV_REGENERATION_DAILY_LIMIT", "").strip()
    if not configured.isdecimal():
        return MANUAL_REGENERATION_LIMIT
    return min(max(int(configured), 1), 100)


def get_regeneration_options_handler(session: SessionDependency) -> GetRegenerationOptionsHandler:
    athlete_races = SqlAlchemyAthleteRaceRepository(session)
    return GetRegenerationOptionsHandler(
        profiles=athlete_races,
        race_goals=athlete_races,
        training_plans=SqlAlchemyTrainingPlanRepository(session),
        runs=SqlAlchemyAgentRunRepository(session),
        quota_limit=_manual_regeneration_limit(),
    )


def _lock_user(session: Session, user_id: str) -> None:
    session.scalar(select(UserModel).where(UserModel.id == user_id).with_for_update())


def get_start_regeneration_handler(session: SessionDependency) -> StartRegenerationHandler:
    athlete_races = SqlAlchemyAthleteRaceRepository(session)
    runs = SqlAlchemyAgentRunRepository(session)
    tasks = SqlAlchemyAgentTaskQueue(session)
    provider, model = resolve_queued_training_plan_provider()
    return StartRegenerationHandler(
        profiles=athlete_races,
        race_goals=athlete_races,
        runs=runs,
        training_plans=SqlAlchemyTrainingPlanRepository(session),
        queue_agent_runs=QueueAgentRunHandler(
            runs=runs,
            queue=tasks,
            prompt_version="running-companion-v1",
            provider=provider,
            model=model,
        ),
        lock_user=lambda user_id: _lock_user(session, user_id),
        quota_limit=_manual_regeneration_limit(),
    )


RegenerationOptionsHandlerDependency = Annotated[
    GetRegenerationOptionsHandler, Depends(get_regeneration_options_handler)
]
StartRegenerationHandlerDependency = Annotated[
    StartRegenerationHandler, Depends(get_start_regeneration_handler)
]
