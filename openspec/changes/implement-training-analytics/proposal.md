## Why

Johnny now has normalized training plans, completed activities, and daily health metrics, but recommendation and Today experiences need deterministic evidence instead of asking an LLM to calculate training state. This change adds repeatable analytics so future AI features can cite stable metrics, handle missing data conservatively, and persist auditable snapshots.

## What Changes

- Add deterministic training analytics for weekly distance, previous weekly distance, mileage ramp rate, acute load, chronic load, and acute-to-chronic load ratio.
- Add deterministic recovery analytics for sleep debt, HRV delta from baseline, resting heart rate delta from baseline, and a conservative readiness label.
- Add a Today context aggregator that combines current training-plan context, recent completed activity, recovery signals, and explicit evidence values.
- Add training metric snapshot persistence through the existing `training_metric_snapshots` table so computed analytics can be audited and reused.
- Add fixed fixtures and tests for formulas, missing-data behavior, Today context aggregation, and snapshot persistence.

## Capabilities

### New Capabilities

- `training-analytics`: Deterministic training load, recovery, readiness, Today context, and analytics snapshot behavior.

### Modified Capabilities

- None.

## Impact

- Backend domain/application analytics services and value objects.
- Application repository interfaces for analytics reads and snapshot persistence.
- SQLAlchemy repository implementation over existing activities, health metrics, training plans, workouts, and training metric snapshots.
- Tests for formula correctness, tenant-scoped persistence, and missing-input behavior.
