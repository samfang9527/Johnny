# Proposal: Agent Runtime and Tools

## Why

Johnny needs AI reasoning, but the agent must operate through safe, testable domain tools rather than raw database access or untracked prompts.

## What Changes

- Add a single Running Companion Agent.
- Add domain tool contracts for reading context and creating proposals.
- Add agent run observability.
- Add safety rules for health and injury-adjacent responses.

## Capabilities

### New Capabilities

- `agent-runtime-tools`

### Modified Capabilities

- `recommendation-approval`
- `training-analytics`
- `persistence-schema`

## Impact

This enables daily AI recommendations and AI coach conversation while preserving deterministic analytics and approval boundaries.

