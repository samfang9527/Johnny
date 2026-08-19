from pathlib import Path
import os
import sys

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


def pytest_configure() -> None:
    os.environ.setdefault("ENV", "test")
    os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")


@pytest.fixture()
def sqlite_engine():
    engine = create_engine("sqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(dbapi_connection, connection_record) -> None:  # noqa: ANN001
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture()
def sqlite_session_factory(sqlite_engine):
    return sessionmaker(bind=sqlite_engine, expire_on_commit=False)
