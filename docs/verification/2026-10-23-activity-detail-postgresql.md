# Task 1 and Task 2 — PostgreSQL verification

The Task 1 probe introduces no database migration. Its ownership and read-only connection checks ran in the backend suite. The account-specific chart/FIT probe used the configured `johnny` connection only for read-only queries; its result is recorded in [Task 3's normalization note](2026-10-23-activity-detail-normalization.md).

For Task 2, a uniquely named empty `johnny_codex_test_*` PostgreSQL database was created solely for verification. Alembic upgraded it from an empty database through `0013_activity_details`. The full backend suite then ran with both `DATABASE_URL` and `JOHNNY_TEST_DATABASE_URL` pointed to that disposable database. This included the isolated-schema PostgreSQL upgrade from `0012_coaching_history` to `0013_activity_details`, checking that prior activity matching data survived, plus the database persistence and concurrency tests that had previously skipped.

Result: **800 passed, 0 skipped, 2 existing deprecation warnings**. The test database was dropped after the suite. A final read-only check found no `johnny_codex_test_*` database remaining; the development `johnny` database still had 59 activity rows, the same count observed before the test run. No migration or test writes were directed at `johnny`.
