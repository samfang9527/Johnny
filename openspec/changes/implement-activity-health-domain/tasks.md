## 1. Activity Domain

- [x] 1.1 Add activity health domain module structure following the existing `src.domain` pattern.
- [x] 1.2 Add completed activity value object with user id, source, optional source activity id, start time, sport type, distance, duration, average pace, average heart rate, elevation gain, and optional matched workout id.
- [x] 1.3 Add activity validation for required load fields, positive distance, positive duration, valid supplied pace, and provider source identifiers.
- [x] 1.4 Add pace derivation from distance meters and duration seconds when average pace is absent.
- [x] 1.5 Add unit tests for manual activity creation, provider activity creation, invalid activity values, derived pace, and supplied pace preservation.

## 2. Health Metric Domain

- [x] 2.1 Add daily health metric value object with user id, metric date, source, sleep duration, sleep quality, HRV, HRV baseline, resting heart rate, and stress score.
- [x] 2.2 Add validation for sparse health metrics and invalid negative recovery values.
- [x] 2.3 Add unit tests for full daily recovery entry, sparse daily recovery entry, and invalid health values.

## 3. Workout Matching

- [x] 3.1 Add date-based activity-to-workout matching service that matches only when exactly one user-owned planned workout exists on the activity date.
- [x] 3.2 Ensure ambiguous same-day workout candidates leave the activity unmatched.
- [x] 3.3 Add service tests for successful same-date matching, no candidate, and ambiguous candidates.

## 4. Repository Contracts

- [x] 4.1 Extend application activity repository protocol with user-scoped methods for saving, loading, and listing activities.
- [x] 4.2 Extend application activity repository protocol with user-scoped methods for saving and loading daily health metrics.
- [x] 4.3 Update SQLAlchemy activity repository mapping between activity domain objects and `ActivityModel`.
- [x] 4.4 Update SQLAlchemy activity repository mapping between daily health domain objects and `HealthMetricModel` rows.
- [x] 4.5 Preserve duplicate provider activity protection and allow multiple manual activities without source activity ids.
- [x] 4.6 Ensure repository reads and writes are scoped by user id for tenant safety.

## 5. Repository Tests

- [x] 5.1 Add repository round-trip tests for manual activities, provider activities, derived pace persistence, source metadata, and ownership filtering.
- [x] 5.2 Add repository tests for duplicate provider activity rejection and multiple manual activity persistence.
- [x] 5.3 Add repository round-trip tests for full and sparse daily health metrics by user id and date.
- [x] 5.4 Add repository/service tests for activity-to-workout matching persistence.
- [x] 5.5 Update metadata or migration tests only if implementation exposes a required persistence schema gap.

## 6. Verification

- [x] 6.1 Run focused activity health domain, matching, and repository tests.
- [x] 6.2 Run the backend test suite.
- [x] 6.3 Run OpenSpec validation for the change.
