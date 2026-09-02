from pathlib import Path
import runpy

from alembic import command
from alembic.config import Config
from sqlalchemy import Column, DateTime, MetaData, String, Table, create_engine, inspect, text


def test_migration_revision_ids_fit_default_alembic_version_column() -> None:
    for migration in Path("backend/migrations/versions").glob("*.py"):
        namespace = runpy.run_path(str(migration))
        assert len(namespace["revision"]) <= 32, migration.name


def test_alembic_upgrade_creates_mvp_schema(tmp_path: Path, monkeypatch) -> None:
    database_path = tmp_path / "johnny_migration.db"
    database_url = f"sqlite:///{database_path}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    config = Config("backend/alembic.ini")
    config.set_main_option("sqlalchemy.url", database_url)

    command.upgrade(config, "head")

    engine = create_engine(database_url)
    table_names = set(inspect(engine).get_table_names())

    assert "alembic_version" in table_names
    assert {
        "users",
        "training_plans",
        "activities",
        "recommendations",
        "agent_runs",
        "agent_tasks",
        "integration_credentials",
    }.issubset(table_names)


def test_root_alembic_config_supports_plain_upgrade_command(tmp_path: Path, monkeypatch) -> None:
    database_path = tmp_path / "johnny_root_migration.db"
    database_url = f"sqlite:///{database_path}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", database_url)

    command.upgrade(config, "head")

    engine = create_engine(database_url)
    table_names = set(inspect(engine).get_table_names())

    assert {
        "alembic_version",
        "users",
        "auth_sessions",
        "password_credentials",
        "agent_tasks",
        "integration_credentials",
    }.issubset(table_names)


def test_async_agent_migration_exposes_queue_columns(tmp_path: Path, monkeypatch) -> None:
    database_path = tmp_path / "johnny_async_agent_migration.db"
    database_url = f"sqlite:///{database_path}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    config = Config("backend/alembic.ini")
    config.set_main_option("sqlalchemy.url", database_url)

    command.upgrade(config, "head")

    engine = create_engine(database_url)
    inspector = inspect(engine)
    task_columns = {column["name"] for column in inspector.get_columns("agent_tasks")}

    assert {
        "id",
        "task_type",
        "status",
        "correlation_id",
        "idempotency_key",
        "payload",
        "available_at",
        "claimed_at",
        "completed_at",
        "failed_at",
        "retry_count",
        "max_attempts",
        "last_error_type",
        "last_error_message",
        "created_at",
        "updated_at",
    }.issubset(task_columns)


def test_async_agent_migration_makes_existing_agent_run_start_nullable(tmp_path: Path, monkeypatch) -> None:
    database_path = tmp_path / "johnny_existing_async_agent_migration.db"
    database_url = f"sqlite:///{database_path}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    engine = create_engine(database_url)
    metadata = MetaData()
    Table(
        "agent_runs",
        metadata,
        Column("id", String(36), primary_key=True),
        Column("started_at", DateTime(timezone=True), nullable=False),
    )
    metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"))
        connection.execute(text("INSERT INTO alembic_version (version_num) VALUES ('0004_add_integration_credentials')"))

    config = Config("backend/alembic.ini")
    config.set_main_option("sqlalchemy.url", database_url)

    command.upgrade(config, "head")

    started_at = next(column for column in inspect(engine).get_columns("agent_runs") if column["name"] == "started_at")
    assert started_at["nullable"] is True
