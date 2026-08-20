from __future__ import annotations

from fastapi import APIRouter

from src.api.dependencies import CurrentUserDependency, MVP_CAPABILITIES
from src.api.schemas.common import DataEnvelope
from src.api.schemas.me import CurrentUserResponse


router = APIRouter(prefix="/api", tags=["me"])


@router.get("/me", response_model=DataEnvelope[CurrentUserResponse])
def get_me(current_user: CurrentUserDependency) -> DataEnvelope[CurrentUserResponse]:
    return DataEnvelope(
        data=CurrentUserResponse(
            id=current_user.id,
            email=current_user.email,
            display_name=current_user.display_name,
            capabilities=MVP_CAPABILITIES,
        )
    )
