from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field


T = TypeVar("T")


class DataEnvelope(BaseModel, Generic[T]):
    data: T


class ApiError(BaseModel):
    code: str
    message: str
    details: list[Any] = Field(default_factory=list)


class ErrorEnvelope(BaseModel):
    error: ApiError


class PageParams(BaseModel):
    limit: int | None = Field(default=None, ge=0, le=100)
    offset: int = Field(default=0, ge=0)
