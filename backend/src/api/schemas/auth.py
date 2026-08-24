from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from src.api.schemas.me import CurrentUserResponse


class EmailPasswordLoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=8, max_length=256)

    @field_validator("email")
    @classmethod
    def email_must_look_like_email(cls, value: str) -> str:
        normalized = value.strip().lower()
        if "@" not in normalized or normalized.startswith("@") or normalized.endswith("@"):
            raise ValueError("email must be valid")
        return normalized


class EmailPasswordSignupRequest(EmailPasswordLoginRequest):
    display_name: str = Field(min_length=1, max_length=200)

    @field_validator("display_name")
    @classmethod
    def display_name_must_not_be_blank(cls, value: str) -> str:
        normalized = " ".join(value.strip().split())
        if not normalized:
            raise ValueError("display name is required")
        return normalized


class AuthUserSessionResponse(BaseModel):
    user: CurrentUserResponse


class GoogleStartResponse(BaseModel):
    authorization_url: str

