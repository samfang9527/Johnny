from __future__ import annotations

from pydantic import BaseModel


class CurrentUserResponse(BaseModel):
    id: str
    email: str | None = None
    display_name: str | None = None
    capabilities: list[str]
