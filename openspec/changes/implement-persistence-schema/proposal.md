# Proposal: Implement Persistence Schema

## Why

Johnny needs a durable PostgreSQL-backed schema before domain services, analytics, recommendations, agent runs, and notification workflows can be trusted. The `02-persistence-schema` change defines the database direction; this change turns that plan into an implementation-ready persistence baseline.

## What Changes

- Add Alembic migration tooling and documented migration commands for local development.
- Replace the current dataclass persistence placeholders with SQLAlchemy ORM models for MVP entities.
- Add PostgreSQL-oriented schema coverage for identity, athlete context, races, training plans, workouts, activities, health metrics, analytics snapshots, recommendations, agent runs, agent run steps, agent context sources, memory, integrations, outbox events, and notifications.
- Model SSO identities without requiring a single auth broker, and model Garmin Connect access as external credential/session references compatible with the latest `garminconnect` package on the Python 3.14 runtime.
- Add an opt-in Garmin Connect schema probe that fetches real activity and health payloads when credentials or a local token-store file are available, then verifies normalized records without persisting raw secrets.
- Add repository interfaces and minimal database-backed implementations so application services do not access sessions directly.
- Add migration, metadata, repository, and constraint tests that prove the schema can be created and core records can be persisted.
- Keep product behavior, API routes, agent execution, frontend UI, and deployed infrastructure changes out of scope.

## Capabilities

### New Capabilities

- `persistence-schema`: Database schema, migrations, ORM models, repository boundaries, and persistence verification for the MVP data backbone.

### Modified Capabilities

- `project-foundation`: Add documented local database migration commands to the existing development baseline.

## Impact

- Affected code: `backend/src/infrastructure/database`, `backend/src/application/interfaces`, new database repository modules, backend tests, backend requirements, Alembic configuration, and project documentation.
- Affected APIs: none; this change does not add product routes.
- Dependencies: add Alembic, PostgreSQL driver support, and `garminconnect==0.3.11` while retaining SQLAlchemy and FastAPI dependencies.
- Systems: local development and test database behavior; Terraform-managed database resources remain out of scope.
