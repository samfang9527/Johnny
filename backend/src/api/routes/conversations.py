from __future__ import annotations

from fastapi import APIRouter

from src.api.dependencies import CurrentUserDependency
from src.api.schemas.common import DataEnvelope
from src.api.schemas.conversations import ConversationMessageRequest, ConversationMessageResponse
from src.application.conversations import SubmitConversationMessageHandler


router = APIRouter(prefix="/api/conversations", tags=["conversations"])


@router.post("/messages", response_model=DataEnvelope[ConversationMessageResponse])
def submit_message(
    payload: ConversationMessageRequest,
    current_user: CurrentUserDependency,
) -> DataEnvelope[ConversationMessageResponse]:
    message = SubmitConversationMessageHandler().handle(user_id=current_user.id, content=payload.content)
    return DataEnvelope(
        data=ConversationMessageResponse(
            message={"user_id": message.user_id, "content": message.content, "recommendation_id": message.recommendation_id},
            run_ref=message.run_ref or "",
        )
    )
