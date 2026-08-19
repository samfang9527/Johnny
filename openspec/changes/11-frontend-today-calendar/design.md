# Design: Frontend Today and Calendar

## Design Status

Discussion required before implementation.

## Approach

Make Today the first screen. Avoid a marketing page. The user should immediately see what matters for today's training decision.

Use Vue, Vite, and TypeScript for this frontend slice. State and API calls should be isolated in Vue composables so Today, Calendar, and later Inbox/Conversation features can share typed data access without coupling UI components to raw fetch calls.

Today sections:

- Race summary and countdown
- Recovery status
- Today's workout
- Johnny's recommendation
- Evidence list
- Decision actions

Calendar sections:

- Week or list-based workout schedule
- Status indicators
- Workout detail panel

## Design Decisions

- Evidence should be visible near the recommendation.
- Actions should be explicit and stateful.
- Empty states should guide setup without long marketing copy.
- Mobile layout should prioritize Today over calendar density.

## Testing Strategy

- Vue component tests for Today loaded, loading, error, and empty states.
- Vue component tests for recommendation actions.
- Calendar rendering tests.
- API client tests with mocked fetch.
- Build verification.

## Risks

- Too much dashboard density can hide the recommendation. Keep hierarchy clear.
- If evidence rendering is inconsistent, trust suffers.
