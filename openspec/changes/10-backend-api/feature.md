# Feature 10: Backend API

## Order

10 of 12. This follows backend domain, analytics, agent, integration, and notification foundations.

## Layer

API/BFF.

## Goal

Expose MVP backend behavior through stable API routes for the frontend and external webhooks.

## Depends On

- `01-project-foundation`
- `02-persistence-schema`
- `03-athlete-race-domain`
- `04-training-plan-domain`
- `05-activity-health-domain`
- `06-training-analytics`
- `07-recommendation-approval`
- `08-agent-runtime-tools`
- `09-integrations-notifications`

## Delivers

- Athlete profile routes
- Race routes
- Training plan and workout routes
- Activity and health routes
- Today context route
- Recommendation decision routes
- Conversation message route
- Integration webhook route

## Non-Goals

- No frontend implementation
- No production auth provider unless separately approved
- No public API versioning beyond MVP path convention

## Design Discussion Required

Before implementation, discuss `design.md` and confirm:

- API path style
- Temporary local auth strategy versus real auth in MVP
- Request/response schema shape
- Error response format

## Testable Outcome

API contract tests cover happy paths and validation errors for all MVP frontend workflows.
