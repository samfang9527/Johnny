from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect


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
    assert {"users", "training_plans", "activities", "recommendations", "agent_runs"}.issubset(table_names)
