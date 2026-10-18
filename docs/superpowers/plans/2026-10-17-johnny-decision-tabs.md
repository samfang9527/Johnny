# Johnny Decision and Tabs Implementation Plan

> **For agentic workers:** Use `superpowers:executing-plans` to implement this plan task by task. The user approved Version E of `frontend/JohnnyDirections.prototype.html` and requested implementation in this session.

**Goal:** Put pending Johnny decisions first and separate advice, review, and history into tabs with progressive disclosure.

**Architecture:** Keep `useJohnny()` and its independent review, advice, and history requests. Restructure `JohnnyPage.vue` only: a decision section precedes a three-tab content area; native disclosures reveal proposal comparison/actions and secondary detail. Reuse the existing buttons, recommendation actions, and design tokens.

**Tech Stack:** Vue 3, TypeScript, Vitest, existing CSS tokens.

**Spec:** User-approved Version E in `frontend/JohnnyDirections.prototype.html?variant=E`; current domain rules in `CONTEXT.md`, `DESIGN.md`, and `UX-CONTRACT.md`.

## Global constraints

- Recommendations must show the exact before/after comparison before acceptance; only explicit acceptance changes the canonical plan.
- Daily Review and Workout Advice retain independent loading, error, freshness, and generation times even when one tab is hidden.
- Execution Score describes plan execution, not fitness, readiness, or injury risk.
- Preserve Traditional Chinese, the five-item app navigation, and the dark ruled training canvas.
- Keep advice request inputs and the history pagination reachable on mobile and by keyboard.

## Review focus

- Multiple pending proposals must each retain their own comparison and actions.
- An absent proposal must give a useful first-screen state.
- Tab switching must not reset form inputs or an opened decision disclosure.
- A hidden tab's updates and errors must appear when it is selected.
- Accept/reject failures must leave the comparison reachable with recovery text.

## Task 1: Behavior tests

**Files:** `frontend/src/JohnnyPage.test.ts`

- [x] Add a test for initial decision-first order, collapsed proposal actions, visible comparison summary, and no-pending state.
- [x] Run the focused test and confirm it fails against the old page.
- [x] Add a test for tab roles, keyboard navigation, disclosure/form persistence, and independent stream updates.
- [x] Run the focused test and confirm the new expectations fail for the intended reason.

## Task 2: Production page and styles

**Files:** `frontend/src/pages/JohnnyPage.vue`, `frontend/src/styles.css`

- [x] Implement the decision-first section and native proposal disclosures using existing recommendation behavior.
- [x] Implement accessible advice, review, and history tabs with roving keyboard focus and persistent mounted panels.
- [x] Put advice inputs and review detail behind disclosures; keep empty, loading, error, and stale states visible in their owning tab.
- [x] Apply the approved Version E hierarchy using existing CSS tokens; verify desktop and narrow mobile layouts.
- [x] Run focused tests until green, then run the full frontend suite and build. The full suite still has 13 App.test.ts failures; the original page had 14 in the same environment.

## Task 3: Durable contract and verification

**Files:** `DESIGN.md`, `UX-CONTRACT.md`

- [x] Replace the old Johnny ordering and simultaneous-visibility prose with the approved decision-first tab behavior.
- [x] Run token drift verification and the strict premium audit without overwriting pre-existing audit output.
- [x] Inspect the production component with fixture data in a browser at desktop and phone widths; check pending, tabs, keyboard, and disclosure states. The no-pending state is covered by the component test.
- [x] Review the final diff and report any remaining limitations.
