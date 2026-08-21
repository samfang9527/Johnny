# Design: Implement Project Foundation

## Context

`01-project-foundation` establishes the MVP baseline: FastAPI backend, Vue/Vite/TypeScript frontend, PostgreSQL configuration, documented local commands, and verified health checks. The current repository already has a FastAPI scaffold under `backend/src`, worker and dispatcher package boundaries, Terraform under `infra/terraform`, and a Vite frontend under `frontend`. The frontend scaffold is still React-based, and the project documentation does not yet give a complete local development path.

This change implements the foundation details without adding Johnny product behavior. It prepares later domain, analytics, agent, API, and frontend changes to build on stable commands and package boundaries.

## Goals / Non-Goals

**Goals:**

- Keep the FastAPI app factory and health/readiness routes as the backend baseline.
- Add or adjust backend tests that verify `/health` and `/ready` through the application entrypoint.
- Convert the frontend scaffold from React to Vue while preserving the Vite/TypeScript build flow and existing environment variable boundary.
- Document backend install, run, test, and smoke commands.
- Document frontend install, dev, build, and preview commands.
- Document local environment variables, including PostgreSQL-oriented `DATABASE_URL` for development and isolated test defaults.

**Non-Goals:**

- Do not introduce Johnny domain models beyond existing placeholders.
- Do not add Alembic migrations in this change; persistence schema work owns migration setup.
- Do not change Terraform resources or deployed runtime behavior.
- Do not add authentication, user profiles, training plans, analytics, agent execution, notifications, or product UI workflows.

## Decisions

### Preserve the Backend Package Shape

Keep `backend/src` as the import root with `main.py` exposing `create_app()` and `app`. Tests should import through that shape instead of creating a separate test-only app.

Alternative considered: move to a new package name or flatten the backend now. That would create churn before domain boundaries are implemented and does not help the foundation goal.

### Verify Health Through FastAPI TestClient

Add focused backend tests for `/health` and `/ready` using FastAPI's test client. These tests prove the app can be constructed and the readiness endpoints remain stable.

Alternative considered: shell-only smoke tests. Shell checks are useful for manual verification, but they are slower and less precise than unit-level route tests for routine development.

### Replace React with Vue in the Existing Vite App

Update `frontend/package.json`, Vite plugin configuration, entrypoint, component files, and TypeScript configuration as needed for Vue single-file components. Keep the existing small status shell as a Vue implementation so the build has real app code to compile.

Alternative considered: create a new frontend directory. Reusing `frontend` keeps existing scripts, environment examples, and future change references stable.

### Document PostgreSQL as the Development Baseline

Use `backend/.env.example` and project docs to show PostgreSQL as the local development database target. Keep test configuration free to use an isolated in-memory default until persistence tests require PostgreSQL.

Alternative considered: require PostgreSQL for all tests immediately. That would slow foundation verification and belongs with the persistence schema change.

### Keep Infrastructure as Documentation-Only

The Terraform scaffold remains unchanged unless documentation needs to point to required environment variables or deployment assumptions.

Alternative considered: introduce database or secret resources now. That would cross into persistence and deployment scope before the app has schema requirements.

## Risks / Trade-offs

- React-to-Vue migration may leave stale React files or dependencies -> verify with file search, dependency metadata, and `npm run build`.
- Backend tests can pass while the manual server command is broken -> include a documented smoke command and run it during implementation when practical.
- PostgreSQL documentation can drift from later persistence defaults -> keep foundation docs limited to variable names and local examples; persistence owns schema and migration behavior.
- Deferring Alembic keeps foundation smaller but delays migration command verification -> call this out explicitly in docs and hand off to `02-persistence-schema`.

## Migration Plan

1. Update backend tests and documentation first, because they do not change runtime behavior.
2. Replace frontend React dependencies and files with Vue equivalents.
3. Run backend tests and frontend build to verify the baseline.
4. Run a local smoke check for backend and frontend startup when the local environment has dependencies installed.
5. Roll back by reverting the frontend dependency/file conversion and documentation changes; no data migration is involved.

## Open Questions

- Should the root README become the primary local setup document, or should it link to separate backend/frontend docs? This design prefers a concise root README unless implementation reveals the commands need more space.
- Should `DATABASE_URL` use a lowercase database name in examples for PostgreSQL convention? This design prefers a clear local example and does not require a specific database name until persistence work.
