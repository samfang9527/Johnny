## Why

`12-frontend-conversation-inbox` defines Johnny's user-initiated conversation and proactive Agent Inbox workflow, but its current design is functional rather than productized. After `DESIGN.md` and the Today visual system, Conversation and Agent Inbox need a Chinese-first implementation contract that preserves Johnny as an evidence-led sports companion instead of turning the app into a generic chatbot.

## What Changes

- Apply `DESIGN.md` to the Conversation and Agent Inbox surfaces.
- Keep `對話` and `Agent 收件匣` visually and behaviorally separate while sharing recommendation, evidence, and action primitives with Today.
- Define Chinese-first message, composer, thread, inbox, recommendation-card, evidence-block, and proposed-action patterns.
- Add conversation layout guidance that keeps Today primary and prevents the chat composer from dominating the product.
- Add Agent Inbox layout guidance for proactive recommendations, priorities, statuses, evidence summaries, expiration, and decision actions.
- Define linked discussion behavior so `討論原因` from Today or Inbox opens or creates a conversation tied to the recommendation.
- Preserve existing backend API contracts; this change is frontend-only unless implementation reveals a missing read/list endpoint that should become a later backend change.

## Capabilities

### New Capabilities

- `frontend-conversation-inbox-visual-design`: Covers the Chinese-first Johnny visual and interaction behavior for Conversation, Agent Inbox, evidence rendering, proposed actions, and linked recommendation discussions.

### Modified Capabilities

None.

## Impact

- Frontend Vue/Vite/TypeScript views, shared components, composables, fixtures, and component tests.
- Reuses `DESIGN.md` runtime tokens and the shared Today visual primitives introduced by `frontend-today-visual-design`.
- Tests must verify Chinese-first copy, separate Conversation and Agent Inbox navigation, evidence/proposed-action rendering, recommendation action consistency, linked discussion navigation, loading/empty/error/busy states, and IME-safe composer behavior.
- No backend API, persistence schema, domain model, or agent runtime changes are included in this proposal.
