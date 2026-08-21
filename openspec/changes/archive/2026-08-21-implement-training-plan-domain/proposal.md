## Why

Johnny can now model athletes and race goals, but it still lacks a validated training calendar that future analytics, recommendations, and Today views can evaluate. Implementing the training plan domain now gives the product a reliable schedule of planned workouts before any AI-generated plan or automatic adjustment behavior is introduced.

## What Changes

- Add domain models for training plans, planned workouts, workout status transitions, and plan adjustment proposals.
- Add validation for plan date ranges, workout scheduling inside plan boundaries, supported workout types, planned workout details, and adjustment proposal payloads.
- Add controlled workout status lifecycle behavior for planned, completed, skipped, and adjusted states.
- Add proposal behavior that preserves before/after workout details and does not mutate workouts until explicit approval/application.
- Connect the domain model to existing persistence tables for `training_plans`, `workouts`, and `plan_adjustments`.
- Add unit and repository integration tests for plan creation, workout ordering, status transitions, adjustment proposals, and persistence round trips.
- Keep AI plan generation, automatic recommendation logic, frontend calendar UI, and integration-based workout matching out of scope.

## Capabilities

### New Capabilities

- `training-plan-domain`: Represents a user's manual or imported training calendar, planned workouts, workout lifecycle states, and explicit adjustment proposals.

### Modified Capabilities

None.

## Impact

- Adds backend domain/application code for training plan and workout behavior.
- Extends the existing training plan repository implementation and protocol coverage.
- Uses existing persistence schema tables where possible; implementation may add the smallest metadata fields or repository helpers if required by domain mapping.
- Adds focused backend unit and integration tests.
