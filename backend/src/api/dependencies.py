from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Annotated, Generator

from fastapi import Cookie, Depends, Header
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
from src.api.errors import ApiUnauthorizedError
from src.application.training_analytics import BuildTodayContextHandler
from src.infrastructure.database.activity_repository import SqlAlchemyActivityRepository
from src.infrastructure.database.agent_run_repository import SqlAlchemyAgentRunRepository
from src.infrastructure.database.athlete_race_repository import SqlAlchemyAthleteRaceRepository
from src.infrastructure.database.auth_repository import SqlAlchemyAuthRepository
from src.infrastructure.database.memory_repository import SqlAlchemyMemoryCandidateRepository
from src.infrastructure.database.models import UserModel
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


SESSION_COOKIE_NAME = "johnny_session"


@dataclass(frozen=True)
class CurrentUser:
    id: str
    email: str | None = None
    display_name: str | None = None


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


SessionDependency = Annotated[Session, Depends(get_session)]


def get_current_user(
    session: SessionDependency,
    session_token: Annotated[str | None, Cookie(alias=SESSION_COOKIE_NAME)] = None,
    user_id: Annotated[str | None, Header(alias="X-Johnny-User-Id")] = None,
    email: Annotated[str | None, Header(alias="X-Johnny-User-Email")] = None,
    display_name: Annotated[str | None, Header(alias="X-Johnny-User-Display-Name")] = None,
) -> CurrentUser:
    if session_token:
        user = SqlAlchemyAuthRepository(session).get_user_by_session_token(session_token)
        if user is not None:
            return CurrentUser(id=user.id, email=user.email, display_name=user.display_name)

    if user_id and _allow_header_user():
        return CurrentUser(
            id=user_id,
            email=email,
            display_name=display_name,
        )

    if _auth_required():
        raise ApiUnauthorizedError("Authentication required")

    return CurrentUser(
        id=user_id or "local-user",
        email=email,
        display_name=display_name,
    )


CurrentUserDependency = Annotated[CurrentUser, Depends(get_current_user)]


def _auth_required() -> bool:
    configured = os.getenv("JOHNNY_AUTH_REQUIRED")
    if configured is not None:
        return configured.strip().lower() in {"1", "true", "yes", "on"}
    return not _running_under_pytest()


def _allow_header_user() -> bool:
    configured = os.getenv("JOHNNY_AUTH_ALLOW_HEADER_USER")
    if configured is not None:
        return configured.strip().lower() in {"1", "true", "yes", "on"}
    return not _auth_required()


def _running_under_pytest() -> bool:
    return os.getenv("ENV", "").strip().lower() == "test" and bool(os.getenv("PYTEST_CURRENT_TEST"))


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
