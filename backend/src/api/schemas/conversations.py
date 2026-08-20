from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class ConversationMessageRequest(BaseModel):
    content: str = Field(min_length=1)

    @field_validator("content")
    @classmethod
    def content_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("conversation message cannot be empty")
        return value


class ConversationMessageResponse(BaseModel):
    message: dict
    run_ref: str
