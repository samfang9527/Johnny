from __future__ import annotations

from typing import Protocol


class UnitOfWork(Protocol):
    def commit(self) -> None:
        ...

    def rollback(self) -> None:
        ...

    @property
    def users(self) -> object:
        ...

    @property
    def training_plans(self) -> object:
        ...

    @property
    def recommendations(self) -> object:
        ...
