from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4


@dataclass(frozen=True)
class ConversationMessage:
    user_id: str
    content: str
    recommendation_id: str | None = None
    run_ref: str | None = None


class SubmitConversationMessageHandler:
    def handle(self, *, user_id: str, content: str, recommendation_id: str | None = None) -> ConversationMessage:
        return ConversationMessage(
            user_id=user_id,
            content=content,
            recommendation_id=recommendation_id,
            run_ref=f"conversation-run-{uuid4()}",
        )
