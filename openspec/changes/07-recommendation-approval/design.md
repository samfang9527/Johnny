# Design: Recommendation and Approval

## Design Status

Discussion required before implementation.

## Approach

Create recommendation workflow before LLM integration. This lets deterministic or fixture-based recommendations exercise the same approval path that agent recommendations will use later.

Recommendation includes:

- Type
- Priority
- Status
- Title and summary
- Evidence list
- Proposed action
- Agent run ID when available
- Decision state

Plan adjustment includes:

- Before payload
- After payload
- Reason
- Status
- Approval timestamp

## Design Decisions

- Significant workout changes require approval.
- Accepting applies the adjustment through an application service.
- Rejecting preserves the recommendation and leaves plan state unchanged.
- Editing creates a revised adjustment payload while preserving the original proposal.

## Testing Strategy

- Unit tests for recommendation lifecycle.
- Service tests for accept, reject, edit, and apply.
- Regression tests proving rejected recommendations do not mutate workouts.
- Persistence tests for recommendation and adjustment history.

## Risks

- If evidence is too free-form, UI and agent evaluation become harder. Keep evidence structured.
- If plan mutation bypasses approval services, trust is weakened.

