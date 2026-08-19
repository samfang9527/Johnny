# Feature 12: Frontend Conversation and Agent Inbox

## Order

12 of 12. This is the final MVP feature slice after Today and calendar are usable.

## Layer

Frontend.

## Goal

Expose Johnny's flexible AI coach conversation and proactive Agent Inbox workflows.

## Depends On

- `01-project-foundation`
- `08-agent-runtime-tools`
- `10-backend-api`
- `11-frontend-today-calendar`

## Delivers

- Conversation list and thread view
- Message composer
- Agent response rendering with evidence and proposed actions
- Agent Inbox list
- Recommendation cards
- Accept, reject, edit, and discuss actions from inbox

## Non-Goals

- No multi-agent UI
- No social/content feed
- No race discovery UI
- No mobile push notification UI

## Design Discussion Required

Before implementation, discuss `design.md` and confirm:

- Conversation and Inbox navigation placement
- Message/evidence rendering style
- How proposed actions appear inside chat
- Inbox priority and expiration display

## Testable Outcome

Frontend tests can render conversation responses, submit a message, show inbox recommendations, and trigger decision actions through mocked APIs.

