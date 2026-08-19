# Feature 07: Recommendation and Approval

## Order

7 of 12. This follows deterministic analytics and precedes agent runtime and API work.

## Layer

Core business logic.

## Goal

Create the human-in-the-loop recommendation workflow: suggest, explain, approve, apply, and record outcome.

## Depends On

- `01-project-foundation`
- `02-persistence-schema`
- `03-athlete-race-domain`
- `04-training-plan-domain`
- `05-activity-health-domain`
- `06-training-analytics`

## Delivers

- Recommendation model behavior
- Evidence payload structure
- Recommendation status lifecycle
- Plan adjustment approval workflow
- Recommendation history
- Daily recommendation service shell

## Non-Goals

- No LLM-generated text required yet
- No notification delivery
- No frontend UI
- No external integrations

## Design Discussion Required

Before implementation, discuss `design.md` and confirm:

- Recommendation types and statuses
- What counts as a significant training change
- Evidence payload shape
- Whether edited recommendations create new adjustment versions

## Testable Outcome

Service tests can create a recommendation from analytics context, accept/reject/edit it, apply an approved plan adjustment, and verify history is preserved.

