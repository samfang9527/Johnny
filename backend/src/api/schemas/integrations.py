from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from src.api.schemas.agent_runs import QueuedAgentRunResponse


class IntegrationConnectionRequest(BaseModel):
    provider: str = Field(min_length=1)
    provider_account_id: str = Field(min_length=1)
    credential_secret_ref: str | None = None


class SyncSummaryResponse(BaseModel):
    resources: dict[str, dict[str, Any]]


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
    sync_status: str = "idle"
    last_sync_started_at: datetime | None = None
    last_sync_completed_at: datetime | None = None
    last_sync_error: str | None = None
    has_partial_failures: bool = False
    sync_warning: str | None = None
    sync_summary: SyncSummaryResponse | None = None
    daily_advice_run: QueuedAgentRunResponse | None = None


class GarminConnectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=1)
    password: str = Field(min_length=1)
    region: Literal["global", "china"] = "global"


class GarminAdminTokenImportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_payload: str = Field(min_length=1)


class ProviderWebhookRequest(BaseModel):
    activities: list[dict[str, Any]] = Field(default_factory=list)
    health: list[dict[str, Any]] = Field(default_factory=list)
    cursor: dict[str, Any] = Field(default_factory=dict)
