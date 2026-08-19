from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import UserModel


class SqlAlchemyUserRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create_user(self, *, email: str, display_name: str) -> UserModel:
        user = UserModel(email=email, display_name=display_name)
        self._session.add(user)
        self._session.flush()
        return user

    def get(self, user_id: str) -> UserModel | None:
        return self._session.get(UserModel, user_id)

    def get_by_email(self, email: str) -> UserModel | None:
        return self._session.scalar(select(UserModel).where(UserModel.email == email))
