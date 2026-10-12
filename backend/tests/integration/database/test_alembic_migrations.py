import json
from pathlib import Path
import runpy

from alembic import command
from alembic.config import Config
from sqlalchemy import JSON, Column, DateTime, ForeignKey, MetaData, String, Table, create_engine, inspect, text


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
        "daily_advices",
    }.issubset(table_names)


def test_daily_advice_migration_has_one_current_row_per_user_day_and_provenance(tmp_path: Path, monkeypatch) -> None:
    database_url = f"sqlite:///{tmp_path / 'daily_advice_migration.db'}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    config = Config("backend/alembic.ini")
    config.set_main_option("sqlalchemy.url", database_url)

    command.upgrade(config, "head")

    inspector = inspect(create_engine(database_url))
    columns = {column["name"] for column in inspector.get_columns("daily_advices")}
    assert {
        "id", "user_id", "advice_date", "state", "data_freshness",
        "reserved_observed_at", "reserved_run_id", "refresh_source_sync_run_id",
        "plan_version_id", "workout_id", "week_start", "week_end", "execution_mode",
        "facts", "week_summary", "today_execution", "workout_guide", "generated_at",
        "source_sync_run_id", "source_run_id", "created_at", "updated_at",
    }.issubset(columns)
    assert any(
        set(unique["column_names"]) == {"user_id", "advice_date"}
        for unique in inspector.get_unique_constraints("daily_advices")
    )
    assert any(
        foreign_key["referred_table"] == "users" and foreign_key["constrained_columns"] == ["user_id"]
        for foreign_key in inspector.get_foreign_keys("daily_advices")
    )


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


def test_profile_experience_migration_converts_unknown_and_weekly_mileage_key(tmp_path: Path, monkeypatch) -> None:
    database_path = tmp_path / "johnny_existing_profile_migration.db"
    database_url = f"sqlite:///{database_path}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    engine = create_engine(database_url)
    metadata = MetaData()
    Table(
        "athlete_profiles",
        metadata,
        Column("id", String(36), primary_key=True),
        Column("user_id", String(36), nullable=False),
        Column("timezone", String(80), nullable=False),
        Column("experience_level", String(80), nullable=False),
        Column("metadata_json", JSON, nullable=False),
    )
    metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"))
        connection.execute(text("INSERT INTO alembic_version (version_num) VALUES ('0006_agent_run_started_nullable')"))
        connection.execute(
            text(
                "INSERT INTO athlete_profiles (id, user_id, timezone, experience_level, metadata_json) "
                "VALUES (:id, :user_id, :timezone, :experience_level, :metadata_json)"
            ),
            {
                "id": "profile-1",
                "user_id": "user-1",
                "timezone": "Asia/Taipei",
                "experience_level": "unknown",
                "metadata_json": '{"current_weekly_mileage": 42, "preferred_training_days": ["sunday"]}',
            },
        )

    config = Config("backend/alembic.ini")
    config.set_main_option("sqlalchemy.url", database_url)

    command.upgrade(config, "head")

    with engine.begin() as connection:
        profile = connection.execute(text("SELECT experience_level, metadata_json FROM athlete_profiles")).mappings().one()

    metadata_json = json.loads(profile["metadata_json"]) if isinstance(profile["metadata_json"], str) else profile["metadata_json"]
    assert profile["experience_level"] is None
    assert metadata_json["current_weekly_mileage_km"] == 42
    assert "current_weekly_mileage" not in metadata_json


def test_child_foreign_key_migration_adds_cascade_delete(tmp_path: Path, monkeypatch) -> None:
    database_path = tmp_path / "johnny_existing_child_cascades.db"
    database_url = f"sqlite:///{database_path}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    engine = create_engine(database_url)
    metadata = MetaData()
    Table(
        "agent_runs",
        metadata,
        Column("id", String(36), primary_key=True),
    )
    Table(
        "agent_run_steps",
        metadata,
        Column("id", String(36), primary_key=True),
        Column("agent_run_id", String(36), ForeignKey("agent_runs.id"), nullable=False),
    )
    Table(
        "agent_context_sources",
        metadata,
        Column("id", String(36), primary_key=True),
        Column("agent_run_id", String(36), ForeignKey("agent_runs.id"), nullable=False),
    )
    Table(
        "training_plans",
        metadata,
        Column("id", String(36), primary_key=True),
    )
    Table(
        "workouts",
        metadata,
        Column("id", String(36), primary_key=True),
        Column("training_plan_id", String(36), ForeignKey("training_plans.id"), nullable=False),
    )
    metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"))
        connection.execute(text("INSERT INTO alembic_version (version_num) VALUES ('0008_training_plan_metadata')"))

    config = Config("backend/alembic.ini")
    config.set_main_option("sqlalchemy.url", database_url)

    command.upgrade(config, "head")

    inspector = inspect(engine)
    expected_foreign_keys = (
        ("agent_run_steps", "agent_runs", ["agent_run_id"]),
        ("agent_context_sources", "agent_runs", ["agent_run_id"]),
        ("workouts", "training_plans", ["training_plan_id"]),
    )
    for table_name, referred_table, constrained_columns in expected_foreign_keys:
        agent_run_fk = next(
            foreign_key
            for foreign_key in inspector.get_foreign_keys(table_name)
            if foreign_key["referred_table"] == referred_table
            and foreign_key["constrained_columns"] == constrained_columns
        )
        assert agent_run_fk["options"]["ondelete"] == "CASCADE"


def test_workout_cascade_migration_runs_from_existing_agent_run_cascade_revision(
    tmp_path: Path, monkeypatch
) -> None:
    database_path = tmp_path / "johnny_existing_0009_revision.db"
    database_url = f"sqlite:///{database_path}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    engine = create_engine(database_url)
    metadata = MetaData()
    Table(
        "training_plans",
        metadata,
        Column("id", String(36), primary_key=True),
    )
    Table(
        "workouts",
        metadata,
        Column("id", String(36), primary_key=True),
        Column("training_plan_id", String(36), ForeignKey("training_plans.id"), nullable=False),
    )
    metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"))
        connection.execute(text("INSERT INTO alembic_version (version_num) VALUES ('0009_agent_run_child_cascade')"))

    config = Config("backend/alembic.ini")
    config.set_main_option("sqlalchemy.url", database_url)

    command.upgrade(config, "head")

    workout_fk = next(
        foreign_key
        for foreign_key in inspect(engine).get_foreign_keys("workouts")
        if foreign_key["referred_table"] == "training_plans"
        and foreign_key["constrained_columns"] == ["training_plan_id"]
    )
    assert workout_fk["options"]["ondelete"] == "CASCADE"
