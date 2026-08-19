# Proposal: Frontend Conversation and Agent Inbox

## Why

Johnny needs both reactive conversation and proactive recommendations, but they should remain separate surfaces so the app does not become a chatbot clone.

## What Changes

- Add Conversation UI for contextual questions.
- Add Agent Inbox UI for proactive recommendations.
- Reuse recommendation action controls from Today.
- Render evidence and proposed actions clearly.

## Capabilities

### New Capabilities

- `frontend-conversation-inbox`

### Modified Capabilities

- `frontend-today-calendar`
- `backend-api`

## Impact

This completes the MVP interaction model: Today, Conversation, and Agent Inbox.

