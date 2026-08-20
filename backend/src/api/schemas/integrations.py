from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class IntegrationConnectionRequest(BaseModel):
    provider: str = Field(min_length=1)
    provider_account_id: str = Field(min_length=1)
    credential_secret_ref: str | None = None


class IntegrationConnectionResponse(BaseModel):
    id: str
    user_id: str
    provider: str
    provider_account_id: str
    status: str
    credential_secret_ref: str | None = None


class ProviderWebhookRequest(BaseModel):
    activities: list[dict[str, Any]] = Field(default_factory=list)
    health: list[dict[str, Any]] = Field(default_factory=list)
    cursor: dict[str, Any] = Field(default_factory=dict)


class SyncSummaryResponse(BaseModel):
    resources: dict[str, dict[str, Any]]
