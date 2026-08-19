## Why

Johnny has deterministic analytics and training-plan persistence, but meaningful plan changes still need an explicit human decision path. This change adds the core recommendation workflow so future agent output can be evidence-backed, auditable, and unable to mutate training plans without approval.

## What Changes

- Add recommendation domain behavior for structured evidence, proposed actions, statuses, priorities, and user decisions.
- Add approval services for accepting, rejecting, and editing recommendation-backed workout adjustments.
- Apply significant workout changes only after an accepted decision, while preserving rejected and edited history.
- Add a daily recommendation service shell that can create fixture/deterministic recommendations from Today context without requiring LLM-generated text.
- Extend repository behavior around recommendation creation, decision recording, ownership checks, and history retrieval.

## Capabilities

### New Capabilities

- `recommendation-approval`: Evidence-backed recommendation lifecycle, user decision workflow, approved plan adjustment application, edit/reject history, and daily recommendation service shell.

### Modified Capabilities

- None.

## Impact

- Backend domain/application recommendation workflow services and value objects.
- Recommendation and training-plan repository interfaces.
- SQLAlchemy recommendation and plan-adjustment persistence behavior.
- Tests for lifecycle transitions, structured evidence, approval application, rejection/edit preservation, and tenant safety.
