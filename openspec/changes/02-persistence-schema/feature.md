# Feature 02: Persistence Schema

## Order

2 of 12. This follows project foundation and precedes domain logic.

## Layer

Database schema and repository foundation.

## Goal

Create the persistent data backbone for users, athletes, races, training plans, workouts, activities, health metrics, analytics snapshots, recommendations, agent runs, memories, integrations, and notifications.

## Depends On

- `01-project-foundation`

## Delivers

- PostgreSQL schema direction
- Migration workflow
- Database models
- Repository interfaces and basic persistence tests
- Auditable timestamps and status fields

## Non-Goals

- No business calculations
- No API routes beyond any required health/config checks
- No agent execution
- No frontend UI

## Design Discussion Required

Before implementation, discuss `design.md` and confirm:

- SQLAlchemy model style and migration workflow
- Whether to store raw integration payloads in database JSON or external object storage references
- UUID strategy
- Timestamp and timezone conventions

## Testable Outcome

The database schema can be migrated, core records can be created and queried through repositories, and schema tests verify required constraints.

