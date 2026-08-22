from __future__ import annotations

from fastapi import APIRouter

from src.api.dependencies import CurrentUserDependency, SessionDependency, build_request_companion_agent, ensure_current_user
from src.api.schemas.common import DataEnvelope
from src.api.schemas.conversations import ConversationMessageRequest, ConversationMessageResponse


router = APIRouter(prefix="/conversations", tags=["conversations"])


@router.post("/messages", response_model=DataEnvelope[ConversationMessageResponse])
def submit_message(
    payload: ConversationMessageRequest,
    current_user: CurrentUserDependency,
    session: SessionDependency,
) -> DataEnvelope[ConversationMessageResponse]:
    ensure_current_user(session, current_user)
    run = build_request_companion_agent(session).run_conversation(user_id=current_user.id, message=payload.content)
    return DataEnvelope(
        data=ConversationMessageResponse(
            message={
                "user_id": current_user.id,
                "content": payload.content,
                "agent_status": run.status,
                "agent_output": run.output_summary or "",
                "recommendation_id": run.recommendation_id,
            },
            run_ref=run.id or "",
        )
    )
