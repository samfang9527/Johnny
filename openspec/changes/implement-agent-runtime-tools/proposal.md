## Why

Johnny now has athlete/race, training plan, activity/health, analytics, and recommendation approval boundaries, but AI reasoning is not yet constrained to safe, observable application tools. This change adds the agent runtime foundation so recommendations and future coach conversations can use structured context without raw database access or untracked prompt behavior.

## What Changes

- Add a single Running Companion Agent runtime for scheduled, reactive, and event-driven runs.
- Add domain tool contracts for reading athlete, training, recovery, and metric context.
- Add proposal-creating write tools for recommendations and workout adjustments.
- Add agent run observability for trigger, model, prompt version, tool calls, result, latency, token usage, and recommendation links.
- Add conservative safety handling for pain, injury-adjacent, and medical-style prompts.
- Keep deterministic analytics and recommendation approval as application/domain boundaries; the agent proposes changes but does not directly mutate training plans.

## Capabilities

### New Capabilities

- `agent-runtime-tools`: Running Companion Agent orchestration, tool access contracts, proposal-only write tools, run observability, and safety boundaries.

### Modified Capabilities

- None.

## Impact

- Adds application-layer agent handlers, tool interfaces, runtime abstractions, and tests.
- Adds infrastructure adapters for fake/test LLM execution and persisted agent run records.
- Uses existing training analytics, recommendation approval, training plan, activity/health, and athlete/race domain models as tool inputs and outputs.
- Extends persistence only where needed for agent run observability; no direct agent database access is allowed.
