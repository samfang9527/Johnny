## Why

The draft-plan plus recommendation-approval flow caused LLM interaction failures because generated training plans were split across two dependent tool calls. That coupling made the model produce brittle `training_plan_creation` recommendation payloads after creating a draft plan, and invalid nested recommendation/action payloads surfaced as `DomainValidationError`.

## What Changes

- Replace the generated-plan write tool with `createTrainingPlan`.
- Store generated training plans as `active` immediately.
- Remove `createRecommendation` from the `training_plan_generation` write allowlist.
- Reject recommendation types/actions that attempt to activate generated draft plans.
- Supersede only overlapping active plans for the same user and race when a generated race plan is created.
- Keep recommendation creation available to separate daily and conversation triggers.

## Capabilities

### Modified Capabilities

- `agent-runtime-tools`: Training-plan generation tool policy, repair behavior, local/OpenAI tool schemas.
- `training-plan-domain`: Direct active generated plan lifecycle and overlapping same-race superseding.
- `recommendation-approval`: Removal of plan-activation recommendation actions.
- `persistence-schema`: Generated plans are represented as active/superseded training plan rows.

## Impact

- Affects backend agent orchestration, domain recommendation validation, training-plan repository behavior, local/OpenAI gateways, tests, and documentation.
- Preserves low-level draft plan persistence for existing domain support, but it is no longer reachable through recommendation approval.
