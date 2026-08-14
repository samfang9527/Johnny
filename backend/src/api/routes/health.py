from __future__ import annotations

from fastapi import APIRouter


router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "Johnny-api"}


@router.get("/ready")
def ready() -> dict[str, str]:
    return {"status": "ready"}

