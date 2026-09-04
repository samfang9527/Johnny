import pytest

from src.domain.recommendation_approval import (
    DomainValidationError,
    EvidenceItem,
    ProposedAction,
    Recommendation,
)


def _evidence() -> tuple[EvidenceItem, ...]:
    return (
        EvidenceItem.create(
            source="training_analytics",
            metric="readiness_label",
            value="rest",
            observed_at="2027-01-28",
            summary="Recovery context indicates rest",
        ),
    )


def _workout_action(*, duration: int = 30) -> ProposedAction:
    before = {
        "id": "workout-1",
        "scheduled_for": "2027-01-28",
        "workout_type": "easy_run",
        "purpose": "Aerobic base",
        "planned_duration_minutes": 45,
        "planned_distance_meters": 8_000,
        "pace_range_seconds_per_km": None,
        "heart_rate_zone": None,
        "status": "planned",
    }
    after = {**before, "planned_duration_minutes": duration}
    return ProposedAction.adjust_workout(
        training_plan_id="plan-1",
        workout_id="workout-1",
        before_payload=before,
        after_payload=after,
        reason="Recovery is low",
    )


def _recommendation(**overrides) -> Recommendation:
    values = {
        "user_id": "user-1",
        "recommendation_type": "workout_adjustment",
        "priority": "high",
        "title": "Reduce today's run",
        "rationale": "Recovery evidence indicates rest.",
        "evidence": _evidence(),
        "proposed_action": _workout_action(),
        "training_plan_id": "plan-1",
        "workout_id": "workout-1",
    }
    values.update(overrides)
    return Recommendation.create(**values)


def test_recommendation_requires_structured_evidence_and_supported_action() -> None:
    recommendation = _recommendation(id="recommendation-1")

    payload = recommendation.to_payload()

    assert recommendation.status == "pending"
    assert recommendation.decision is None
    assert recommendation.training_plan_id == "plan-1"
    assert payload["evidence"]["items"][0]["metric"] == "readiness_label"
    assert payload["proposed_action"]["type"] == "adjust_workout"
    assert payload["proposed_action"]["after_payload"]["planned_duration_minutes"] == 30


def test_recommendation_rejects_malformed_evidence_and_action_payloads() -> None:
    with pytest.raises(DomainValidationError, match="evidence source"):
        EvidenceItem.create(source="", metric="readiness_label", value="rest")

    with pytest.raises(DomainValidationError, match="action type"):
        ProposedAction.create(action_type="unsupported", payload={})

    with pytest.raises(DomainValidationError, match="training plan"):
        ProposedAction.adjust_workout(
            training_plan_id="",
            workout_id="workout-1",
            before_payload={"id": "workout-1"},
            after_payload={"id": "workout-1", "planned_duration_minutes": 30},
            reason="Recovery is low",
        )


def test_informational_recommendation_allows_no_plan_change_action() -> None:
    recommendation = Recommendation.create(
        user_id="user-1",
        recommendation_type="informational",
        priority="low",
        title="No change needed",
        rationale="Training context is stable.",
        evidence=_evidence(),
        proposed_action=ProposedAction.no_plan_change(reason="No meaningful change is required."),
    )

    assert recommendation.training_plan_id is None
    assert recommendation.workout_id is None
    assert recommendation.proposed_action.action_type == "no_plan_change"


def test_proposed_action_accepts_legacy_action_type_payload_key() -> None:
    action = ProposedAction.from_payload({"action_type": "no_plan_change", "reason": "Legacy informational row"})

    assert action.action_type == "no_plan_change"
    assert action.to_payload() == {"type": "no_plan_change", "reason": "Legacy informational row"}


def test_recommendation_rejects_training_plan_creation_type_and_action() -> None:
    with pytest.raises(DomainValidationError, match="action type"):
        ProposedAction.create(
            action_type="create_training_plan",
            payload={
                "draft_training_plan_id": "plan-draft-1",
                "reason": "A plan is needed.",
                "summary": "Four-week race build.",
            },
        )

    with pytest.raises(DomainValidationError, match="recommendation type"):
        Recommendation.create(
            user_id="user-1",
            recommendation_type="training_plan_creation",
            priority="medium",
            title="Review generated plan",
            rationale="The generated plan matches the target race.",
            evidence=_evidence(),
            proposed_action=ProposedAction.no_plan_change(reason="Training plans are created by a separate workflow."),
        )


def test_recommendation_lifecycle_accepts_rejects_and_blocks_final_decisions() -> None:
    accepted = _recommendation().accept()
    rejected = _recommendation().reject()

    assert accepted.status == "decided"
    assert accepted.decision == "accepted"
    assert rejected.status == "decided"
    assert rejected.decision == "rejected"

    with pytest.raises(DomainValidationError, match="pending"):
        accepted.reject()


def test_editing_preserves_original_and_creates_revised_pending_recommendation() -> None:
    original = _recommendation(id="recommendation-1")
    revised_action = _workout_action(duration=20)

    edited, revised = original.edit(revised_action)

    assert edited.id == "recommendation-1"
    assert edited.status == "decided"
    assert edited.decision == "edited"
    assert edited.proposed_action.payload["after_payload"]["planned_duration_minutes"] == 30
    assert edited.evidence == original.evidence
    assert revised.id is None
    assert revised.status == "pending"
    assert revised.decision is None
    assert revised.proposed_action.payload["after_payload"]["planned_duration_minutes"] == 20
    assert revised.proposed_action.payload["supersedes_recommendation_id"] == "recommendation-1"
