# Proposal: Implement Project Foundation

## Why

The `01-project-foundation` change defines the MVP development baseline, but the repository still needs the concrete scaffold alignment that makes later changes reliable. This change turns that foundation decision into an implementation-ready plan for backend health checks, Vue/Vite frontend setup, documented local commands, and environment configuration.

## What Changes

- Align the existing frontend scaffold with Vue, Vite, and TypeScript for MVP development.
- Preserve the current FastAPI backend structure and verify the health and readiness endpoints through tests.
- Document local setup, run, build, smoke, and test commands for backend and frontend work.
- Normalize local environment examples around PostgreSQL as the MVP database while keeping test-only in-memory configuration isolated.
- Keep infrastructure behavior unchanged except for documentation links or environment variable references needed by the foundation baseline.

## Capabilities

### New Capabilities

- `project-foundation-implementation`: Implementation-ready baseline for local development commands, Vue frontend scaffold, PostgreSQL-oriented configuration, and backend health verification.

### Modified Capabilities

- None

## Impact

- Affected code: `backend/src`, `backend/tests`, `backend/.env.example`, `frontend/src`, `frontend/package.json`, `frontend/vite.config.ts`, `frontend/.env.example`, and project documentation.
- Affected APIs: existing `/health` and `/ready` endpoints remain stable; no product API behavior is added.
- Dependencies: replace React frontend dependencies with Vue/Vite equivalents; backend dependencies remain focused on FastAPI, testing, and current infrastructure abstractions.
- Systems: local development only; deployed infrastructure remains out of scope for this change.
