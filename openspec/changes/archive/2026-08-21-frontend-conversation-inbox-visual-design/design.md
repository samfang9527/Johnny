## Context

`12-frontend-conversation-inbox` adds Johnny's two secondary AI surfaces: user-initiated `對話` and proactive `Agent 收件匣`. The current active change defines functional scope, while `DESIGN.md` and the accepted `frontend-today-visual-design` spec define the Chinese-first visual system, `decision strip`, stable recommendation action labels, and shared primitive expectations.

The existing frontend already has a top navigation shell and visual primitives from the Today visual implementation. This change should extend those primitives rather than creating a second chat-specific design system. The result must make Conversation useful without letting a composer become the product's center of gravity; Today remains the daily decision cockpit.

## Goals / Non-Goals

**Goals:**

- Apply `DESIGN.md` to `對話` and `Agent 收件匣`.
- Keep Conversation and Agent Inbox separate surfaces with clear user intent: questions in Conversation, proactive recommendations in Inbox.
- Reuse Today primitives for recommendation cards, evidence lists, status badges, buttons, loading panels, empty states, and error states.
- Implement a Chinese-first conversation layout with thread list, message history, composer, Johnny responses, evidence blocks, and proposed action cards.
- Implement Agent Inbox with pending and historical recommendations, priority, status, evidence summary, expiration where present, and stable decision actions.
- Support `討論原因` from Today or Inbox by opening or creating a linked conversation tied to a recommendation.
- Add tests for message submit, IME-safe composer behavior, evidence rendering, inbox states, recommendation actions, and linked discussion navigation.

**Non-Goals:**

- No multi-agent UI or agent picker.
- No social feed, race discovery, news feed, or push notification UI.
- No backend route changes in this proposal.
- No full conversation persistence UX beyond the backend contract currently available.
- No redesign of the Today cockpit or `資料來源` surface.

## Decisions

1. **Keep Conversation secondary to Today.**

   The `對話` route should look like an analytical support surface: compact thread list, clear message history, and evidence/proposed-action cards. The composer stays visible but does not become a full-screen prompt box.

   Alternative considered: make Conversation the default app layout. Rejected because Johnny's product concept explicitly avoids a ChatGPT clone and places Today first.

2. **Use a two-pane layout on desktop and stacked layout on mobile.**

   Desktop Conversation uses thread list plus active thread. Mobile starts with the active thread and exposes thread selection as a compact section or route state. Inbox uses a list/detail rhythm on desktop and card stack on mobile.

   Alternative considered: single full-width chat transcript everywhere. Rejected because Inbox and linked recommendation context need more structured scanning than a transcript-only design.

3. **Render Johnny responses with evidence and proposed actions as structured blocks.**

   Johnny messages can include prose, evidence blocks, and proposed action cards. Evidence blocks use the shared evidence list typography; proposed actions use the recommendation action vocabulary from `DESIGN.md`.

   Alternative considered: render evidence inline inside chat bubbles. Rejected because evidence would be harder to scan and would reduce trust in recommendations.

4. **Make Agent Inbox a proactive decision queue, not a notification feed.**

   Inbox cards must show priority, recommendation summary, evidence, status, expiration if present, and decision actions. Historical statuses such as accepted, rejected, edited, expired, and applied should remain visible but quieter than pending items.

   Alternative considered: chronological notification feed. Rejected because the main user task is resolving recommendations, not reading activity logs.

5. **Use linked conversation state for `討論原因`.**

   Choosing `討論原因` from Inbox opens or creates a conversation whose context includes the recommendation id, title, and evidence summary. If the backend only returns a message or run reference, the frontend still presents it as a linked thread state.

   Alternative considered: open a generic composer with copied text. Rejected because the recommendation relationship would be easy to lose.

6. **Composer must be app-owned and IME-safe.**

   Forms use `novalidate`, inline Chinese validation, stable button geometry, and explicit composition handling so Enter-to-submit never fires during Chinese input selection.

   Alternative considered: native validation and default textarea keyboard behavior. Rejected because it creates inconsistent copy and can break Chinese-first input.

## Risks / Trade-offs

- **Risk: Conversation visually dominates the MVP.** -> Mitigation: keep Today as default, use a compact composer, and use structured recommendation/evidence blocks instead of an oversized prompt surface.
- **Risk: Inbox duplicates Today recommendation UI.** -> Mitigation: reuse the same shared recommendation action and evidence primitives, with Inbox-specific list/detail framing.
- **Risk: Backend conversation API is minimal.** -> Mitigation: use typed frontend fixtures and adapter boundaries; do not invent persistence behavior that the API does not provide.
- **Risk: Linked discussion context is lost.** -> Mitigation: include recommendation id and summary in frontend linked-thread state and in the discuss API request.
- **Risk: Chinese input submits prematurely.** -> Mitigation: test composition start/end behavior and block Enter submit while composing.

