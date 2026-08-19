## 1. Approval and Baseline Review

- [x] 1.1 Review `openspec/changes/implement-project-foundation/design.md` with the product owner and receive explicit approval before implementation.
- [x] 1.2 Inspect the current backend, frontend, environment examples, and README so implementation starts from the latest scaffold state.

## 2. Backend Health Verification

- [x] 2.1 Add focused FastAPI tests that construct the application through `backend/src/main.py`.
- [x] 2.2 Verify `GET /health` returns a successful response with the expected reachable API payload.
- [x] 2.3 Verify `GET /ready` returns a successful response with the expected readiness payload.
- [x] 2.4 Remove or replace any placeholder backend tests that no longer prove foundation behavior.

## 3. Vue Frontend Scaffold

- [x] 3.1 Replace React runtime, React type, and React Vite plugin dependencies with Vue and the Vue Vite plugin in `frontend/package.json`.
- [x] 3.2 Update Vite and TypeScript configuration for Vue single-file component compilation.
- [x] 3.3 Convert the current frontend entrypoint and status shell from `.tsx` React components to Vue/TypeScript files.
- [x] 3.4 Search the frontend scaffold and remove stale React imports, components, and user-facing scaffold text.

## 4. Local Configuration and Documentation

- [x] 4.1 Update backend environment examples to document local host, port, PostgreSQL `DATABASE_URL`, and infrastructure-related optional variables.
- [x] 4.2 Update frontend environment examples to document the local API base URL and app name variables.
- [x] 4.3 Expand project documentation with backend install, run, test, and smoke commands.
- [x] 4.4 Expand project documentation with frontend install, dev, build, and preview commands.
- [x] 4.5 Note that Alembic migration setup is deferred to `02-persistence-schema`.

## 5. Verification

- [x] 5.1 Run backend tests and confirm the health/readiness tests pass.
- [x] 5.2 Run the frontend build and confirm Vue/Vite/TypeScript compilation succeeds.
- [x] 5.3 Run a local smoke check for backend and frontend startup when dependencies are installed.
- [x] 5.4 Confirm no product behavior, database migration, authentication flow, agent behavior, notification integration, or Terraform resource change was introduced.
