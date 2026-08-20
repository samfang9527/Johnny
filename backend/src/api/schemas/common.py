from __future__ import annotations

from collections.abc import Sequence
from typing import Annotated, Any, Generic, TypeVar

from fastapi import Query
from pydantic import BaseModel, Field


T = TypeVar("T")
DEFAULT_PAGE_LIMIT = 20
MAX_PAGE_LIMIT = 100
PageLimit = Annotated[int, Query(ge=1, le=MAX_PAGE_LIMIT)]
PageOffset = Annotated[int, Query(ge=0)]


class DataEnvelope(BaseModel, Generic[T]):
    data: T


class PagingMeta(BaseModel):
    limit: int
    offset: int
    has_next: bool


class ListEnvelope(BaseModel, Generic[T]):
    data: list[T]
    paging: PagingMeta


class ApiError(BaseModel):
    code: str
    message: str
    details: list[Any] = Field(default_factory=list)


class ErrorEnvelope(BaseModel):
    error: ApiError


class PageParams(BaseModel):
    limit: int = Field(default=DEFAULT_PAGE_LIMIT, ge=1, le=MAX_PAGE_LIMIT)
    offset: int = Field(default=0, ge=0)


def page_query_limit(limit: int = DEFAULT_PAGE_LIMIT) -> int:
    return limit + 1


def list_envelope(items: Sequence[T], *, limit: int, offset: int) -> ListEnvelope[T]:
    has_next = len(items) > limit
    return ListEnvelope(
        data=list(items[:limit]),
        paging=PagingMeta(limit=limit, offset=offset, has_next=has_next),
    )
