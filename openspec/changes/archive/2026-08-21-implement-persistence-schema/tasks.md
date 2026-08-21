## 1. Approval and Baseline Review

- [x] 1.1 Review `openspec/changes/implement-persistence-schema/design.md` with the product owner and receive explicit approval before implementation.
- [x] 1.2 Inspect the current backend database placeholders, repository interfaces, test configuration, and README before editing source files.
- [x] 1.3 Confirm the local PostgreSQL test database URL to use for migration and repository verification.

## 2. Dependencies and Migration Tooling

- [x] 2.1 Add Alembic and PostgreSQL driver dependencies to backend requirements.
- [x] 2.2 Add backend-owned Alembic configuration and migration environment files.
- [x] 2.3 Wire Alembic metadata to the backend SQLAlchemy declarative base.
- [x] 2.4 Add the initial migration revision for the MVP persistence schema.

## 3. SQLAlchemy Model Foundation

- [x] 3.1 Replace dataclass persistence placeholders with SQLAlchemy declarative model infrastructure.
- [x] 3.2 Add shared UUID, timestamp, status, JSON metadata, and naming conventions.
- [x] 3.3 Add identity and athlete context models: users, auth identities, athlete profiles, and memory items.
- [x] 3.4 Add race and plan models: races, training plans, workouts, and plan adjustments.
- [x] 3.5 Add data models: activities, health metrics, and training metric snapshots.
- [x] 3.6 Add recommendation and agent models: recommendations, agent runs, agent run steps, and agent context sources.
- [x] 3.7 Add async, integration, and notification models: outbox events, integration connections with Garmin Connect credential/session lifecycle metadata, sync runs, notification intents, and notification deliveries.

## 4. Repository Boundaries

- [x] 4.1 Add application repository interfaces for the core persistence flows needed by later MVP changes.
- [x] 4.2 Add SQLAlchemy-backed repository implementations that hide session management from application services.
- [x] 4.3 Add or update unit-of-work support for commit, rollback, and repository access.
- [x] 4.4 Ensure repositories expose minimal create, get, list, relationship loading, and status update methods required by the specs.

## 5. Documentation

- [x] 5.1 Document local migration upgrade, downgrade, current revision, and history commands.
- [x] 5.2 Document local and test database URL environment variables.
- [x] 5.3 Note that API routes, frontend UI, agent execution, notification delivery, and Terraform database resources remain out of scope.

## 6. Verification

- [x] 6.1 Add metadata tests that assert all MVP table groups exist with expected key columns.
- [x] 6.2 Add migration tests that create an empty database schema from Alembic revisions.
- [x] 6.3 Add repository tests for creating, loading, listing, and updating core records.
- [x] 6.4 Add constraint tests for required foreign keys, duplicate provider activity identifiers, and status fields.
- [x] 6.8 Add provider-neutral SSO identity and Garmin Connect credential/session metadata tests.
- [x] 6.9 Add opt-in Garmin Connect payload normalization verification using `garminconnect==0.3.11`.
- [x] 6.10 Add provider-neutral integration resource cursor persistence for independent data stream sync progress.
- [x] 6.5 Run the backend persistence test suite with the configured PostgreSQL test database.
- [x] 6.6 Run the full backend test suite and confirm existing foundation tests still pass.
- [x] 6.7 Run `openspec validate --all` and confirm the change remains valid.
