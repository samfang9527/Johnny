from __future__ import annotations

from datetime import date, datetime
from typing import Protocol

from src.domain.training_plan import PlanAdjustmentProposal, TrainingPlan


class TrainingPlanStore(Protocol):
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

    def get_current_plan_for_user(self, user_id: str) -> TrainingPlan | None:
        ...

    def get_plan_for_user(self, user_id: str, plan_id: str | None) -> TrainingPlan | None:
        ...

    def save_plan(self, user_id: str, plan: TrainingPlan) -> TrainingPlan:
        ...

    def create_active_plan(self, user_id: str, plan: TrainingPlan) -> TrainingPlan:
        ...

    def create_draft_plan(self, user_id: str, plan: TrainingPlan) -> TrainingPlan:
        ...

    def activate_draft_plan(
        self,
        user_id: str,
        plan_id: str | None,
        *,
        accepted_at: date,
        conflict_created_after: datetime | None = None,
    ) -> TrainingPlan | None:
        ...

    def create_adjustment_proposal(
        self,
        user_id: str,
        proposal: PlanAdjustmentProposal,
    ) -> PlanAdjustmentProposal | None:
        ...

    def list_adjustment_proposals_for_plan(
        self,
        user_id: str,
        training_plan_id: str | None,
        *,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[PlanAdjustmentProposal]:
        ...
