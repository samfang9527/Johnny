# Feature 11: Frontend Today and Calendar

## Order

11 of 12. This follows backend API and precedes conversation/inbox frontend completion.

## Layer

Frontend.

## Goal

Build the main product surface for the MVP: Today, race context, recovery evidence, today's workout, recommendation actions, and training calendar.

## Depends On

- `01-project-foundation`
- `10-backend-api`

## Delivers

- App shell
- Today page
- Race goal summary
- Recovery evidence display
- Today's workout display
- Recommendation action controls
- Training calendar view
- API client integration for these surfaces
- Vue components and composables for Today and Calendar workflows

## Non-Goals

- No chat UI
- No Agent Inbox UI
- No integration settings UI
- No marketing landing page

## Design Discussion Required

Before implementation, discuss `design.md` and confirm:

- Today page information hierarchy
- Recommendation evidence component shape
- Calendar density and mobile behavior
- Empty states before data exists

## Testable Outcome

Frontend tests can render Today and calendar states from mocked API responses and verify recommendation actions call the correct API methods.
