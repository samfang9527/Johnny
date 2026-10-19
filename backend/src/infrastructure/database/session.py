from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker


def get_database_url() -> str:
    load_local_env()
    database_url = os.getenv("DATABASE_URL")
    if os.getenv("ENV", "").strip().lower() == "production" and not (database_url and database_url.startswith("postgresql+psycopg://")):
        raise RuntimeError("A PostgreSQL DATABASE_URL is required in production")
    return database_url or "sqlite:///./app.db"


def get_test_database_url() -> str:
    return os.getenv("JOHNNY_TEST_DATABASE_URL", get_database_url())


def create_database_engine(database_url: str | None = None) -> Engine:
    url = database_url or get_database_url()
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    return create_engine(url, connect_args=connect_args)


def create_session_factory(database_url: str | None = None) -> sessionmaker[Session]:
    return sessionmaker(bind=create_database_engine(database_url), expire_on_commit=False)


def load_local_env() -> None:
    if os.getenv("ENV", "").strip().lower() in {"test", "production"}:
        return
    env_file = Path(__file__).resolve().parents[3] / ".env"
    if not env_file.exists():
        return
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv(env_file, override=False)
