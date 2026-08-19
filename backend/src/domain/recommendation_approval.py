from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any


RECOMMENDATION_TYPES = frozenset({"workout_adjustment", "recovery_warning", "informational"})
PRIORITIES = frozenset({"low", "medium", "high"})
STATUSES = frozenset({"pending", "decided", "superseded"})
DECISIONS = frozenset({"accepted", "rejected", "edited"})
ACTION_TYPES = frozenset({"adjust_workout", "no_plan_change"})


class DomainValidationError(ValueError):
    """Raised when recommendation approval data cannot support safe decisions."""


@dataclass(frozen=True)
class EvidenceItem:
    source: str
    metric: str
    value: Any
    unit: str | None = None
    observed_at: str | None = None
    summary: str | None = None

    def __post_init__(self) -> None:
        if not self.source:
            raise DomainValidationError("evidence source is required")
        if not self.metric:
            raise DomainValidationError("evidence metric is required")
        if self.value is None:
            raise DomainValidationError("evidence value is required")

    @classmethod
    def create(
        cls,
        *,
        source: str,
        metric: str,
        value: Any,
        unit: str | None = None,
        observed_at: str | None = None,
        summary: str | None = None,
    ) -> EvidenceItem:
        return cls(
            source=source,
            metric=metric,
            value=value,
            unit=unit,
            observed_at=observed_at,
            summary=summary,
        )

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> EvidenceItem:
        return cls.create(
            source=payload.get("source", ""),
            metric=payload.get("metric", ""),
            value=payload.get("value"),
            unit=payload.get("unit"),
            observed_at=payload.get("observed_at"),
            summary=payload.get("summary"),
        )

    def to_payload(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "metric": self.metric,
            "value": self.value,
            "unit": self.unit,
            "observed_at": self.observed_at,
            "summary": self.summary,
        }


@dataclass(frozen=True)
class ProposedAction:
    action_type: str
    payload: dict[str, Any]

    def __post_init__(self) -> None:
        if self.action_type not in ACTION_TYPES:
            raise DomainValidationError("action type is not supported")
        if self.action_type == "adjust_workout":
            _validate_adjust_workout(self.payload)
        if self.action_type == "no_plan_change" and not self.payload.get("reason"):
            raise DomainValidationError("no plan change action requires a reason")
        object.__setattr__(self, "payload", dict(self.payload))

    @classmethod
    def create(cls, *, action_type: str, payload: dict[str, Any]) -> ProposedAction:
        return cls(action_type=action_type, payload=payload)

    @classmethod
    def adjust_workout(
        cls,
        *,
        training_plan_id: str,
        workout_id: str,
        before_payload: dict[str, Any],
        after_payload: dict[str, Any],
        reason: str,
    ) -> ProposedAction:
        return cls.create(
            action_type="adjust_workout",
            payload={
                "training_plan_id": training_plan_id,
                "workout_id": workout_id,
                "before_payload": dict(before_payload),
                "after_payload": dict(after_payload),
                "reason": reason,
            },
        )

    @classmethod
    def no_plan_change(cls, *, reason: str) -> ProposedAction:
        return cls.create(action_type="no_plan_change", payload={"reason": reason})

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> ProposedAction:
        return cls.create(action_type=payload.get("type", ""), payload=payload)

    def with_metadata(self, metadata: dict[str, Any]) -> ProposedAction:
        return replace(self, payload={**self.payload, **metadata})

    def to_payload(self) -> dict[str, Any]:
        return {"type": self.action_type, **self.payload}


@dataclass(frozen=True)
class Recommendation:
    user_id: str
    recommendation_type: str
    priority: str
    title: str
    rationale: str
    evidence: tuple[EvidenceItem, ...]
    proposed_action: ProposedAction
    status: str = "pending"
    decision: str | None = None
    training_plan_id: str | None = None
    workout_id: str | None = None
    agent_run_id: str | None = None
    id: str | None = None

    def __post_init__(self) -> None:
        if not self.user_id:
            raise DomainValidationError("user id is required")
        if self.recommendation_type not in RECOMMENDATION_TYPES:
            raise DomainValidationError("recommendation type is not supported")
        if self.priority not in PRIORITIES:
            raise DomainValidationError("priority is not supported")
        if not self.title:
            raise DomainValidationError("title is required")
        if not self.rationale:
            raise DomainValidationError("rationale is required")
        if not self.evidence:
            raise DomainValidationError("evidence is required")
        if self.status not in STATUSES:
            raise DomainValidationError("status is not supported")
        if self.decision is not None and self.decision not in DECISIONS:
            raise DomainValidationError("decision is not supported")
        if self.status == "pending" and self.decision is not None:
            raise DomainValidationError("pending recommendation cannot have a decision")
        if self.status == "decided" and self.decision is None:
            raise DomainValidationError("decided recommendation requires a decision")
        if self.proposed_action.action_type == "adjust_workout":
            plan_id = self.training_plan_id or self.proposed_action.payload.get("training_plan_id")
            workout_id = self.workout_id or self.proposed_action.payload.get("workout_id")
            if not plan_id:
                raise DomainValidationError("workout adjustment requires training plan")
            if not workout_id:
                raise DomainValidationError("workout adjustment requires workout")
            object.__setattr__(self, "training_plan_id", plan_id)
            object.__setattr__(self, "workout_id", workout_id)
        object.__setattr__(self, "evidence", tuple(self.evidence))

    @classmethod
    def create(
        cls,
        *,
        user_id: str,
        recommendation_type: str,
        priority: str,
        title: str,
        rationale: str,
        evidence: tuple[EvidenceItem, ...],
        proposed_action: ProposedAction,
        status: str = "pending",
        decision: str | None = None,
        training_plan_id: str | None = None,
        workout_id: str | None = None,
        agent_run_id: str | None = None,
        id: str | None = None,
    ) -> Recommendation:
        return cls(
            id=id,
            user_id=user_id,
            recommendation_type=recommendation_type,
            priority=priority,
            title=title,
            rationale=rationale,
            evidence=evidence,
            proposed_action=proposed_action,
            status=status,
            decision=decision,
            training_plan_id=training_plan_id,
            workout_id=workout_id,
            agent_run_id=agent_run_id,
        )

    @classmethod
    def from_payload(
        cls,
        *,
        id: str | None,
        user_id: str,
        title: str,
        rationale: str,
        status: str,
        decision: str | None,
        evidence_payload: dict[str, Any],
        training_plan_id: str | None = None,
    ) -> Recommendation:
        metadata = evidence_payload.get("recommendation", {})
        action_payload = evidence_payload.get("proposed_action", {"type": "no_plan_change", "reason": "No action."})
        return cls.create(
            id=id,
            user_id=user_id,
            recommendation_type=metadata.get("type", "informational"),
            priority=metadata.get("priority", "medium"),
            title=title,
            rationale=rationale,
            evidence=tuple(EvidenceItem.from_payload(item) for item in evidence_payload.get("items", ())),
            proposed_action=ProposedAction.from_payload(action_payload),
            status=status,
            decision=decision,
            training_plan_id=training_plan_id,
            workout_id=action_payload.get("workout_id"),
            agent_run_id=metadata.get("agent_run_id"),
        )

    def accept(self) -> Recommendation:
        self._ensure_pending()
        return replace(self, status="decided", decision="accepted")

    def reject(self) -> Recommendation:
        self._ensure_pending()
        return replace(self, status="decided", decision="rejected")

    def edit(self, revised_action: ProposedAction) -> tuple[Recommendation, Recommendation]:
        self._ensure_pending()
        edited = replace(self, status="decided", decision="edited")
        revised = replace(
            self,
            id=None,
            status="pending",
            decision=None,
            proposed_action=revised_action.with_metadata({"supersedes_recommendation_id": self.id}),
        )
        return edited, revised

    def to_payload(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "recommendation_type": self.recommendation_type,
            "priority": self.priority,
            "title": self.title,
            "rationale": self.rationale,
            "status": self.status,
            "decision": self.decision,
            "training_plan_id": self.training_plan_id,
            "workout_id": self.workout_id,
            "agent_run_id": self.agent_run_id,
            "evidence": {"items": [item.to_payload() for item in self.evidence]},
            "proposed_action": self.proposed_action.to_payload(),
        }

    def to_evidence_payload(self) -> dict[str, Any]:
        return {
            "items": [item.to_payload() for item in self.evidence],
            "proposed_action": self.proposed_action.to_payload(),
            "recommendation": {
                "type": self.recommendation_type,
                "priority": self.priority,
                "workout_id": self.workout_id,
                "agent_run_id": self.agent_run_id,
            },
        }

    def _ensure_pending(self) -> None:
        if self.status != "pending":
            raise DomainValidationError("recommendation must be pending")


def _validate_adjust_workout(payload: dict[str, Any]) -> None:
    if not payload.get("training_plan_id"):
        raise DomainValidationError("workout adjustment requires training plan")
    if not payload.get("workout_id"):
        raise DomainValidationError("workout adjustment requires workout")
    if not payload.get("before_payload"):
        raise DomainValidationError("workout adjustment requires before payload")
    if not payload.get("after_payload"):
        raise DomainValidationError("workout adjustment requires after payload")
    if not payload.get("reason"):
        raise DomainValidationError("workout adjustment requires reason")
