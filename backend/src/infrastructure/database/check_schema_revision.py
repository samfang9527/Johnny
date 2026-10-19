"""Fail a deployment when Alembic has not reached this image's migration head."""

from __future__ import annotations

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text

from src.infrastructure.database.session import create_database_engine


def main() -> int:
    config = Config(str(Path(__file__).resolve().parents[3] / "alembic.ini"))
    expected = set(ScriptDirectory.from_config(config).get_heads())
    engine = create_database_engine()
    try:
        with engine.connect() as connection:
            current = connection.scalar(text("SELECT version_num FROM alembic_version"))
    finally:
        engine.dispose()
    if current not in expected:
        raise SystemExit("Database migration revision does not match the release image")
    print("Database migration revision matches release image")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
