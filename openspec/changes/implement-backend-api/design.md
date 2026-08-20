## Context

The backend currently exposes only `/health` and `/ready` from `src.main:create_app()`. The domain, application handlers, SQLAlchemy repositories, Garmin-compatible ingestion, recommendation approval, notification, and agent tooling foundations already exist, so this change should add a thin FastAPI/BFF layer over those boundaries.

The frontend-facing scope comes from `10-backend-api`: athlete profile, races, training plans, workouts, activities, health metrics, Today context, recommendations, conversations, and integration webhook entry points. Production SSO is intentionally out of scope; this API should use a local/test current-user dependency that can later be replaced by real authentication without changing route handlers.

## Goals / Non-Goals

**Goals:**

- Provide stable MVP HTTP routes and typed schemas for the frontend and webhook workflows.
- Keep route handlers thin: validate input, resolve current user, call application handlers/stores, and serialize responses.
- Use a consistent JSON envelope for success and structured errors for validation, not found, conflict, and domain validation failures.
- Preserve tenant safety by deriving user scope from the current-user dependency and passing it into application/repository calls.
- Add contract tests for route status codes, response shapes, tenant misses, validation failures, and key domain side effects.

**Non-Goals:**

- Do not add production SSO, Firebase verification, session management, or authorization policy beyond the temporary current-user boundary.
- Do not build frontend screens.
- Do not introduce public API versioning beyond an MVP `/api` route prefix.
- Do not replace existing application handlers with route-specific business logic.

## Decisions

1. Use FastAPI routers grouped by product workflow.

   Routes should live under `backend/src/api/routes/` and be included by `create_app()`. Keep router files focused by workflow: `me`, `athlete_profile`, `races`, `training_plans`, `activities`, `today`, `recommendations`, `conversations`, and `integrations`. This follows the existing health route pattern and prevents one large route file.

   Alternative considered: one large MVP router. It is faster initially, but it repeats the earlier repository-file problem and makes contract tests harder to navigate.

2. Add API schema modules separate from domain models.

   Request/response models should live under `backend/src/api/schemas/`. Domain dataclasses remain internal and API responses intentionally control field names, nullable fields, and JSON serialization. This also protects the frontend from incidental domain refactors.

   Alternative considered: return domain dataclasses directly. That leaks internal shapes and creates avoidable churn when domain models evolve.

3. Use application handlers/services as route dependencies.

   Route handlers should depend on application-facing abstractions and handler factories. They may use the SQLAlchemy unit of work and repositories through dependency wiring, but they should not inline database queries. This preserves testability and keeps API behavior aligned with existing use cases.

   Alternative considered: call repositories directly from routes. That is acceptable for very small CRUD APIs, but this project already has application handlers for recommendation decisions, Today context, integrations, notifications, and analytics.

4. Use a temporary current-user dependency.

   The MVP API should resolve a user from a local/test header such as `X-Johnny-User-Id`, with a deterministic test fallback only when the app is in test/local mode. The dependency should be isolated in `api/dependencies.py` so production auth can replace it later.

   Alternative considered: implement real SSO now. The product has already separated identity provider design from this change; adding it here would expand the API work and block frontend contracts.

5. Standardize response and error envelopes.

   Successful responses should be predictable for the frontend, and errors should use a shared structure with `code`, `message`, and optional `details`. Validation errors should preserve field-level details from FastAPI/Pydantic while normalizing the top-level shape.

   Alternative considered: rely on FastAPI default errors. Defaults are workable for humans but inconsistent as frontend contracts.

6. Keep webhook routes provider-neutral.

   Integration webhook endpoints should accept a provider path segment and route to the existing ingestion boundary. Garmin polling remains compatible with `garminconnect`; webhook shape should not assume Garmin-only payloads.

   Alternative considered: add Garmin-specific route names. That would make the first provider easy but force route churn when additional providers are added.

## Risks / Trade-offs

- Auth placeholder leaks into product assumptions -> Keep the current-user dependency explicit, documented, and easy to replace.
- API scope grows into full CRUD for every table -> Implement only MVP workflows required by the source change and tests.
- Response schemas duplicate domain fields -> Accept this duplication because it protects the external contract.
- Webhook behavior depends on incomplete real provider contracts -> Use fake/sample payloads and provider-neutral command boundaries first.
- Conversation routes may be thinner than future agent runtime needs -> Return stable message/run references now and defer streaming or long-running orchestration to a later change.

## Migration Plan

1. Add schema, dependency, and route modules behind the existing FastAPI app factory.
2. Add tests with `TestClient(create_app())`, dependency overrides, and fake handlers/stores where useful.
3. Wire repository-backed dependencies for integration tests without changing existing table schemas.
4. Keep existing `/health` and `/ready` behavior unchanged.
5. Rollback is removing the new router includes and route/schema modules; no database migration is expected.

## Open Questions

- Confirm the exact MVP route prefix: this design assumes `/api` for product routes while leaving `/health` and `/ready` at the root.
- Confirm the local current-user header name before implementation. This design recommends `X-Johnny-User-Id`.
- Confirm whether conversation submission should synchronously return an agent response stub or an accepted run/message reference for asynchronous follow-up.
