# Feature 06: Training Analytics

## Order

6 of 12. This follows activity and health data and precedes AI recommendations.

## Layer

Core business logic.

## Goal

Compute deterministic training and recovery metrics that Johnny can use as evidence.

## Depends On

- `01-project-foundation`
- `02-persistence-schema`
- `03-athlete-race-domain`
- `04-training-plan-domain`
- `05-activity-health-domain`

## Delivers

- Weekly distance
- Previous weekly distance
- Mileage ramp rate
- Acute and chronic load
- Sleep debt
- HRV and resting HR deltas
- Recovery/readiness label
- Today context aggregator

## Non-Goals

- No LLM reasoning
- No final recommendation generation
- No advanced race prediction
- No frontend charts

## Design Discussion Required

Before implementation, discuss `design.md` and confirm:

- Exact formulas for MVP training load
- Readiness labels and thresholds
- Conservative behavior when data is missing
- Whether analytics snapshots are generated on demand or persisted daily

## Testable Outcome

Analytics tests compute expected metrics from fixed activity and health data fixtures.

