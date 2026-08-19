# Proposal: Training Analytics

## Why

Johnny should not ask the LLM to calculate core training metrics. Deterministic analytics make recommendations explainable, testable, and safer.

## What Changes

- Add deterministic analytics services.
- Add Today context aggregation.
- Persist analytics snapshots for auditability and fast retrieval.

## Capabilities

### New Capabilities

- `training-analytics`

### Modified Capabilities

- `activity-health-domain`
- `training-plan-domain`
- `persistence-schema`

## Impact

This produces the structured evidence used by recommendations, agent tools, API responses, and Today UI.

