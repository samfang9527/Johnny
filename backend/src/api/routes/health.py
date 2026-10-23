from __future__ import annotations

import os

from fastapi import APIRouter, HTTPException
from sqlalchemy import text

from src.infrastructure.database.session import create_database_engine
from src.application.task_contracts import CURRENT_CONTRACT_VERSION


router = APIRouter()


def _worker_contract() -> dict:
    build = os.getenv('JOHNNY_BUILD_SHA', 'unknown')
    return {'build': build, 'versions': [0, CURRENT_CONTRACT_VERSION]}


@router.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "Johnny-api",
            'worker_contract': _worker_contract()}


@router.get("/ready")
def ready() -> dict:
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
    return {"status": "ready", 'worker_contract': _worker_contract()}
