from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, Generator

from fastapi import Depends, Header
from sqlalchemy.orm import Session

from src.infrastructure.database.models import UserModel
from src.infrastructure.database.session import create_session_factory


MVP_CAPABILITIES = [
    "athlete-profile",
    "races",
    "training-plans",
    "activities",
    "today",
    "recommendations",
    "conversations",
    "integrations",
]


@dataclass(frozen=True)
class CurrentUser:
    id: str
    email: str | None = None
    display_name: str | None = None


def get_current_user(
    user_id: Annotated[str | None, Header(alias="X-Johnny-User-Id")] = None,
    email: Annotated[str | None, Header(alias="X-Johnny-User-Email")] = None,
    display_name: Annotated[str | None, Header(alias="X-Johnny-User-Display-Name")] = None,
) -> CurrentUser:
    return CurrentUser(
        id=user_id or "local-user",
        email=email,
        display_name=display_name,
    )


_session_factory = create_session_factory()


def get_session() -> Generator[Session]:
    session = _session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


CurrentUserDependency = Annotated[CurrentUser, Depends(get_current_user)]
SessionDependency = Annotated[Session, Depends(get_session)]


def ensure_current_user(session: Session, current_user: CurrentUser) -> UserModel:
    user = session.get(UserModel, current_user.id)
    if user is None:
        user = UserModel(
            id=current_user.id,
            email=current_user.email or f"{current_user.id}@local.johnny",
            display_name=current_user.display_name or current_user.id,
        )
        session.add(user)
        session.flush()
    return user
