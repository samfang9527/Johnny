from __future__ import annotations

from typing import Protocol


class UserStore(Protocol):
    def create_user(self, *, email: str, display_name: str) -> object:
        ...

    def get(self, user_id: str) -> object | None:
        ...
