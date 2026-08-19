# Feature 01: Project Foundation

## Order

1 of 12. This must be completed before database, domain, API, or frontend feature work.

## Layer

Tech stack and project foundation.

## Goal

Prepare the existing scaffold for MVP development with clear local commands, configuration boundaries, test entry points, and application package conventions.

## Depends On

No MVP feature dependencies.

## Delivers

- Confirmed backend package layout
- Confirmed Vue/Vite frontend package layout
- Environment variable contract
- Local development commands
- Test commands for backend and frontend
- Base configuration strategy
- Health-check baseline

## Non-Goals

- No user-facing product behavior
- No database schema beyond connection configuration
- No agent runtime
- No third-party integrations

## Design Discussion Required

Before implementation, discuss `design.md` and confirm:

- Whether to keep Python/FastAPI for MVP
- How to migrate the current frontend scaffold to Vue/Vite for MVP
- Whether to introduce Alembic now
- Which local PostgreSQL and queue services are required for development

## Testable Outcome

A developer can install dependencies, run the backend, run the frontend, run tests, and confirm the health endpoint works.
