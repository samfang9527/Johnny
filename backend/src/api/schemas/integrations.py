from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class IntegrationConnectionRequest(BaseModel):
    provider: str = Field(min_length=1)
    provider_account_id: str = Field(min_length=1)
    credential_secret_ref: str | None = None


class IntegrationConnectionResponse(BaseModel):
    id: str
    user_id: str
    provider: str
    provider_account_id: str
    provider_display_name: str | None = None
    status: str
    credential_secret_ref: str | None = None
    credential_format: str | None = None
    credential_status: str = "active"


class GarminConnectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=1)
    password: str = Field(min_length=1)
    region: Literal["global", "china"] = "global"


class ProviderWebhookRequest(BaseModel):
    activities: list[dict[str, Any]] = Field(default_factory=list)
    health: list[dict[str, Any]] = Field(default_factory=list)
    cursor: dict[str, Any] = Field(default_factory=dict)


class SyncSummaryResponse(BaseModel):
    resources: dict[str, dict[str, Any]]
