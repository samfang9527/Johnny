## 1. Design Gate and Shared Foundations

- [x] 1.1 Review `openspec/changes/frontend-conversation-inbox-visual-design/design.md` with the product owner and receive explicit approval before implementation.
- [x] 1.2 Extend frontend types and fixtures for conversation threads, messages, Johnny responses, linked recommendations, inbox recommendations, priorities, statuses, and expiration metadata.
- [x] 1.3 Confirm existing shared primitives from Today cover buttons, status badges, evidence rows, loading panels, empty states, error states, and recommendation actions.
- [x] 1.4 Add or update tests that guard stable Chinese recommendation action labels across Today, Conversation, and Agent Inbox.

## 2. Conversation Surface

- [x] 2.1 Implement the `對話` view as a two-pane desktop layout with thread list, active message history, compact composer, and stacked mobile behavior.
- [x] 2.2 Render Johnny messages with prose, structured evidence blocks, and proposed action cards using `DESIGN.md` data typography and shared primitives.
- [x] 2.3 Implement app-owned composer validation with `novalidate`, inline Chinese validation copy, stable submit button geometry, and no native browser validation bubbles.
- [x] 2.4 Implement IME-safe Enter behavior so composition events do not submit Traditional Chinese input prematurely.
- [x] 2.5 Wire non-empty message submission to the conversation API boundary and show stable loading, error, and returned run-reference states.
- [x] 2.6 Add component tests for conversation loading, empty, error, thread switching, message submit, validation, IME composition, evidence rendering, and proposed action rendering.

## 3. Agent Inbox

- [x] 3.1 Implement the `Agent 收件匣` view as a proactive recommendation decision queue separate from Conversation.
- [x] 3.2 Render pending recommendations with priority, title, summary, evidence summary, status, expiration when present, and stable recommendation actions.
- [x] 3.3 Render accepted, rejected, edited, expired, and applied recommendations in a quieter historical state without competing with pending recommendations.
- [x] 3.4 Add a Chinese-first empty inbox state explaining that future proactive suggestions will appear in `Agent 收件匣`.
- [x] 3.5 Add component tests for pending, historical, empty, status, priority, expiration, and mobile-safe inbox rendering.

## 4. Linked Recommendation Discussion

- [x] 4.1 Implement `討論原因` from Agent Inbox so it opens or creates a `對話` state linked to the selected recommendation.
- [x] 4.2 Display linked recommendation context in Conversation, including recommendation title, status, and evidence summary.
- [x] 4.3 Wire the discuss action to the existing recommendation discuss API boundary where available.
- [x] 4.4 Add navigation tests proving Inbox `討論原因` opens Conversation with preserved recommendation context.

## 5. Visual and Accessibility Consistency

- [x] 5.1 Verify Conversation and Agent Inbox use `DESIGN.md` tokens through shared CSS variables rather than screen-local palette literals.
- [x] 5.2 Ensure all enabled interactive controls have hover, active, disabled, busy, and keyboard focus-visible states.
- [x] 5.3 Verify long Traditional Chinese, mixed English provider names, long recommendation titles, and evidence summaries wrap without clipping on mobile.
- [x] 5.4 Verify Conversation and Inbox loading, empty, error, success, busy, and reduced-motion states preserve stable layout geometry.

## 6. Verification

- [x] 6.1 Run OpenSpec validation for `frontend-conversation-inbox-visual-design` and fix all errors.
- [x] 6.2 Run the official `DESIGN.md` linter, frontend-design-premium strict audit, and token drift verification after any visual or token changes.
- [x] 6.3 Run frontend tests and production build.
- [x] 6.4 Inspect the implemented Conversation and Agent Inbox screens in a browser at desktop and narrow mobile widths.
- [x] 6.5 Update task checkboxes only after each item is implemented and verified.
