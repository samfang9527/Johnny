from __future__ import annotations

from datetime import date
from typing import Protocol


class TrainingPlanRepository(Protocol):
    def create_plan(
        self,
        *,
        user_id: str,
        race_id: str | None,
        name: str,
        starts_on: date,
        ends_on: date,
    ) -> object:
        ...

    def get_current_plan_for_user(self, user_id: str) -> object | None:
        ...
