import os

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

from src.infrastructure.database.models import Base
from src.infrastructure.database.recommendation_repository import SqlAlchemyRecommendationRepository
from src.infrastructure.database.session import create_session_factory
from src.infrastructure.database.uow import SqlAlchemyUnitOfWork
from src.infrastructure.database.user_repository import SqlAlchemyUserRepository


def test_postgresql_migrations_and_repositories_with_configured_database(monkeypatch) -> None:
    database_url = os.getenv("JOHNNY_TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("JOHNNY_TEST_DATABASE_URL is not configured")
    monkeypatch.setenv("DATABASE_URL", database_url)

    engine = create_engine(database_url)
    Base.metadata.drop_all(engine)
    with engine.begin() as connection:
        connection.execute(text("DROP TABLE IF EXISTS alembic_version"))

    config = Config("backend/alembic.ini")
    config.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(config, "head")

    table_names = set(inspect(engine).get_table_names())
    assert {"users", "recommendations", "agent_runs", "alembic_version"}.issubset(table_names)

    session_factory = create_session_factory(database_url)
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        user = SqlAlchemyUserRepository(uow.session).create_user(
            email="postgres-runner@example.com",
            display_name="Postgres Runner",
        )
        recommendation = SqlAlchemyRecommendationRepository(uow.session).create_recommendation(
            user_id=user.id,
            title="Use PostgreSQL verification",
            rationale="The configured test database is available",
            evidence={"database": "postgresql"},
        )
        uow.commit()

    with SqlAlchemyUnitOfWork(session_factory) as uow:
        loaded = SqlAlchemyRecommendationRepository(uow.session).get(recommendation.id)

        assert loaded is not None
        assert loaded.user_id == user.id
        assert loaded.evidence == {"database": "postgresql"}
