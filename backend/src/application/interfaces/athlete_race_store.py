from __future__ import annotations

from datetime import date
from typing import Protocol

from src.domain.athlete_race import AthleteProfile, RaceGoal


class AthleteProfileStore(Protocol):
    def save_profile(self, user_id: str, profile: AthleteProfile) -> AthleteProfile:
        ...

    def get_profile_for_user(self, user_id: str) -> AthleteProfile | None:
        ...


class RaceGoalStore(Protocol):
    def create_race_goal(self, user_id: str, race_goal: RaceGoal) -> RaceGoal:
        ...

    def list_race_goals_for_user(
        self,
        user_id: str,
        *,
        race_date_from: date | None = None,
        race_date_to: date | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[RaceGoal]:
        ...

    def get_race_goal_for_user(self, user_id: str, race_goal_id: str | None) -> RaceGoal | None:
        ...

    def update_race_goal(self, user_id: str, race_goal: RaceGoal) -> RaceGoal | None:
        ...
