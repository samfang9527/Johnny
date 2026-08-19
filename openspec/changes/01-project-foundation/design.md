# Design: Project Foundation

## Design Status

Discussion required before implementation.

## Approach

Keep the current backend scaffold as the MVP base and change the frontend direction to Vue/Vite:

- Backend: Python and FastAPI under `backend/src`
- Frontend: Vue, Vite, and TypeScript under `frontend/src`
- Infrastructure: existing Terraform direction under `infra/terraform`
- Worker/dispatcher: existing abstractions under `backend/src/worker` and `backend/src/dispatcher`

The foundation change should make the backend scaffold reliable and plan the frontend scaffold migration from React to Vue before product UI work starts.

## Decisions to Confirm

- Keep the current Python/FastAPI backend for MVP.
- Use Vue/Vite/TypeScript for the MVP frontend.
- Replace the current React scaffold during the foundation feature rather than during product UI features.
- Use PostgreSQL as the required MVP database in local and deployed environments.
- Add Alembic migration support during persistence work, not before, unless the team wants database migration commands available immediately.
- Use environment variables for database URL, queue settings, LLM provider configuration, and notification credentials.

## Testing Strategy

- Backend unit test verifies the health endpoint.
- Frontend build verifies Vue, TypeScript, and Vite configuration.
- A documented local smoke check verifies backend and frontend startup.

## Risks

- Switching stacks now would delay product validation.
- Deferring migration setup too long would make schema work harder. This design keeps migration setup adjacent to persistence.
