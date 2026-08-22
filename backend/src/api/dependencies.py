from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, Generator

from fastapi import Depends, Header
from sqlalchemy.orm import Session

from src.application.agent_runtime import RunningCompanionAgent
from src.application.agent_tools import (
    AgentToolRegistry,
    AthleteContextTool,
    CreateRecommendationTool,
    MemoryCandidateTool,
    RecentActivitiesTool,
    RecoveryStateTool,
    TodayWorkoutTool,
    TrainingMetricsTool,
    TrainingPlanTool,
    WorkoutAdjustmentProposalTool,
)
from src.application.training_analytics import BuildTodayContextHandler
from src.infrastructure.database.models import UserModel
from src.infrastructure.database.activity_repository import SqlAlchemyActivityRepository
from src.infrastructure.database.agent_run_repository import SqlAlchemyAgentRunRepository
from src.infrastructure.database.athlete_race_repository import SqlAlchemyAthleteRaceRepository
from src.infrastructure.database.memory_repository import SqlAlchemyMemoryCandidateRepository
from src.infrastructure.database.recommendation_repository import SqlAlchemyRecommendationRepository
from src.infrastructure.database.session import create_session_factory
from src.infrastructure.database.training_plan_repository import SqlAlchemyTrainingPlanRepository
from src.infrastructure.llm.composition import build_running_companion_agent
from src.infrastructure.llm.local_gateway import LocalCompanionModelGateway
from src.infrastructure.llm.settings import load_llm_settings


MVP_CAPABILITIES = [
    "athlete-profile",
    "races",
    "training-plans",
    "activities",
    "today",
    "recommendations",
    "conversations",
    "integrations",
]


@dataclass(frozen=True)
class CurrentUser:
    id: str
    email: str | None = None
    display_name: str | None = None


def get_current_user(
    user_id: Annotated[str | None, Header(alias="X-Johnny-User-Id")] = None,
    email: Annotated[str | None, Header(alias="X-Johnny-User-Email")] = None,
    display_name: Annotated[str | None, Header(alias="X-Johnny-User-Display-Name")] = None,
) -> CurrentUser:
    return CurrentUser(
        id=user_id or "local-user",
        email=email,
        display_name=display_name,
    )


_session_factory = create_session_factory()


def get_session() -> Generator[Session]:
    session = _session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


CurrentUserDependency = Annotated[CurrentUser, Depends(get_current_user)]
SessionDependency = Annotated[Session, Depends(get_session)]


def ensure_current_user(session: Session, current_user: CurrentUser) -> UserModel:
    user = session.get(UserModel, current_user.id)
    if user is None:
        user = UserModel(
            id=current_user.id,
            email=current_user.email or f"{current_user.id}@local.johnny",
            display_name=current_user.display_name or current_user.id,
        )
        session.add(user)
        session.flush()
    return user


def build_request_companion_agent(session: Session) -> RunningCompanionAgent:
    activities = SqlAlchemyActivityRepository(session)
    training_plans = SqlAlchemyTrainingPlanRepository(session)
    athlete_races = SqlAlchemyAthleteRaceRepository(session)
    recommendations = SqlAlchemyRecommendationRepository(session)
    today_context = BuildTodayContextHandler(training_data=activities, training_plans=training_plans)
    tools = AgentToolRegistry(
        (
            AthleteContextTool(profiles=athlete_races, race_goals=athlete_races),
            TrainingPlanTool(training_plans=training_plans),
            TodayWorkoutTool(today_context=today_context),
            RecentActivitiesTool(activities=activities),
            RecoveryStateTool(today_context=today_context),
            TrainingMetricsTool(today_context=today_context),
            CreateRecommendationTool(recommendations=recommendations),
            WorkoutAdjustmentProposalTool(recommendations=recommendations),
            MemoryCandidateTool(memory_candidates=SqlAlchemyMemoryCandidateRepository(session)),
        )
    )
    settings = load_llm_settings()
    if settings is not None:
        return build_running_companion_agent(
            run_store=SqlAlchemyAgentRunRepository(session),
            tools=tools,
            prompt_version="running-companion-v1",
            settings=settings,
        )
    return RunningCompanionAgent(
        run_store=SqlAlchemyAgentRunRepository(session),
        model_gateway=LocalCompanionModelGateway(),
        tools=tools,
        prompt_version="running-companion-v1",
        provider="local",
        model="deterministic-local-companion",
    )
