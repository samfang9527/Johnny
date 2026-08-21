## 1. Analytics Domain

- [x] 1.1 Add training analytics value objects for metric windows, unavailable signals, training load summary, recovery context, readiness evidence, Today context, and training metric snapshots.
- [x] 1.2 Add fixed activity and health metric fixtures that cover current week, previous week, twenty-eight-day load, missing health data, and cross-user data.
- [x] 1.3 Add unit tests for weekly distance, previous weekly distance, mileage ramp percentage, zero-denominator behavior, acute load, chronic load, and acute-to-chronic ratio.
- [x] 1.4 Implement deterministic training load calculations using normalized `CompletedActivity` objects and explicit anchor-date windows.
- [x] 1.5 Add unit tests for sleep debt, HRV delta, derived resting heart rate baseline/delta, stress evidence, and readiness label thresholds.
- [x] 1.6 Implement recovery context calculations with explicit unavailable-signal handling and conservative `unknown`, `ready`, `caution`, and `rest` labels.

## 2. Application Services

- [x] 2.1 Define application repository interfaces needed to list user activities by date range, list user daily health metrics by date range, load the current training plan, and save/load analytics snapshots.
- [x] 2.2 Add tests for Today context aggregation with planned workout, recent activity evidence, recovery context, training load metrics, and no generated prose.
- [x] 2.3 Implement `TodayContextService` to compose training plan, workout, activity, health, training load, recovery, and missing-data evidence for a trusted `user_id` and anchor date.
- [x] 2.4 Add tests that analytics services exclude other users' activities, health metrics, plans, workouts, and snapshots.

## 3. Persistence

- [x] 3.1 Extend SQLAlchemy repositories with tenant-scoped date-range reads for activities and daily health metrics.
- [x] 3.2 Add a SQLAlchemy analytics snapshot repository over `TrainingMetricSnapshotModel` with save, get, and list-by-user behavior.
- [x] 3.3 Add persistence tests for snapshot JSON payloads, snapshot type filtering, captured timestamp ordering, and user ownership checks.
- [x] 3.4 Verify existing database metadata and migrations still match without adding a new migration.

## 4. Verification

- [x] 4.1 Run the focused training analytics unit and integration tests.
- [x] 4.2 Run the full backend test suite.
- [x] 4.3 Run `openspec validate implement-training-analytics`.
