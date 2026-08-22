## Why

The MVP backend now has domain, persistence, analytics, agent, integration, and notification foundations, but the frontend still needs stable HTTP contracts to use those workflows. This change turns the internal application handlers into typed API endpoints so the Today view, planning workflows, recommendation approvals, conversations, and provider webhooks can be built against one coherent backend surface.

## What Changes

- Add FastAPI route groups for health, current user context, athlete profiles, races, training plans, workouts, activities, health metrics, Today context, recommendations, conversations, and integration webhooks.
- Add typed request and response schemas for MVP frontend workflows.
- Add structured API error responses for validation failures, missing resources, tenant-scope misses, and domain validation failures.
- Route handlers call application handlers or application-facing services rather than SQLAlchemy repositories directly.
- Add a temporary local/test user strategy suitable for MVP development while keeping production SSO/auth provider work outside this change.
- Add contract and validation tests for each route group.

## Capabilities

### New Capabilities

- `backend-api`: Stable MVP HTTP API contracts for frontend workflows, recommendation decisions, conversation entry points, and provider webhook ingestion.

### Modified Capabilities

- None.

## Impact

- Affects backend API modules, dependency wiring, request/response schema modules, and API integration tests.
- Depends on existing domain/application behavior from project foundation, persistence schema, athlete/race, training plan, activity/health, training analytics, recommendation approval, agent runtime tools, and integrations/notifications.
- Does not add production authentication, frontend implementation, or public API versioning beyond the MVP path convention.
