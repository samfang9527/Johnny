## 1. Training Plan Domain

- [x] 1.1 Add training plan domain module structure following the existing `src.domain` pattern.
- [x] 1.2 Add training plan value object with user id, optional race id, name, status, start date, end date, and ordered workouts.
- [x] 1.3 Add validation for plan date ranges and workout dates inside plan boundaries.
- [x] 1.4 Add unit tests for valid manual plan creation, workout ordering, invalid date ranges, and out-of-bound workouts.

## 2. Workout Domain

- [x] 2.1 Add workout value object with scheduled date, supported type, purpose, planned duration, planned distance, optional pace range, optional heart-rate zone, and status.
- [x] 2.2 Define MVP supported workout types and planned workout load validation.
- [x] 2.3 Add controlled workout status transition behavior for planned, adjusted, completed, and skipped states.
- [x] 2.4 Add unit tests for supported workout details, unsupported workout types, missing planned load, valid transitions, and invalid transitions.

## 3. Adjustment Proposals

- [x] 3.1 Add plan adjustment proposal value object with user id, plan id, optional workout id, before payload, after payload, status, and optional recommendation id.
- [x] 3.2 Add proposal status transition behavior for proposed, approved, rejected, and applied states.
- [x] 3.3 Ensure proposal creation does not mutate workout domain objects.
- [x] 3.4 Add unit tests for proposal creation, approval, rejection, applied status, invalid transitions, and no implicit workout mutation.

## 4. Repository Contracts

- [x] 4.1 Extend the application training plan repository protocol with user-scoped methods for saving/loading plans with workouts.
- [x] 4.2 Extend the application training plan repository protocol with user-scoped methods for creating and listing adjustment proposals.
- [x] 4.3 Update SQLAlchemy training plan repository mapping between domain objects and `TrainingPlanModel`/`WorkoutModel`.
- [x] 4.4 Update SQLAlchemy training plan repository mapping between adjustment proposal domain objects and `PlanAdjustmentModel`.
- [x] 4.5 Ensure repository reads and writes are scoped by user id for tenant safety.

## 5. Repository Tests

- [x] 5.1 Add repository round-trip tests for training plan creation, loading by user id, workout ordering, and ownership filtering.
- [x] 5.2 Add repository round-trip tests for workout detail payloads and status persistence.
- [x] 5.3 Add repository round-trip tests for adjustment proposal creation, listing, status persistence, before payloads, after payloads, and ownership filtering.
- [x] 5.4 Update metadata or migration tests only if implementation exposes a required persistence schema gap.

## 6. Verification

- [x] 6.1 Run focused training plan domain and repository tests.
- [x] 6.2 Run the backend test suite.
- [x] 6.3 Run OpenSpec validation for the change.
