from __future__ import annotations

import os

from fastapi import APIRouter, HTTPException
from sqlalchemy import text

from src.infrastructure.database.session import create_database_engine


router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "Johnny-api"}


@router.get("/ready")
def ready() -> dict[str, str]:
    if os.getenv("ENV", "").strip().lower() == "production":
        try:
            engine = create_database_engine()
            try:
                with engine.connect() as connection:
                    revision = connection.scalar(text("SELECT version_num FROM alembic_version"))
                    users, tasks = connection.execute(text("SELECT to_regclass('public.users'), to_regclass('public.agent_tasks')")).one()
            finally:
                engine.dispose()
            if not revision or not users or not tasks:
                raise RuntimeError("Required database schema is missing")
        except Exception as exc:
            raise HTTPException(status_code=503, detail="Database is not ready") from exc
    return {"status": "ready"}
