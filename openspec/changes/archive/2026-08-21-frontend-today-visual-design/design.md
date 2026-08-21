## Context

The current frontend is a Vue/Vite scaffold with a starter app shell. `11-frontend-today-calendar` defines the functional Today and Calendar workflow: race countdown, recovery evidence, today's workout, recommendation actions, and a calendar-oriented schedule. `DESIGN.md` now defines Johnny's Chinese-first visual identity: a dark training cockpit, `decision strip` recommendation pattern, stable Chinese action vocabulary, and a first-class `資料來源` surface for binding data providers.

The implementation must preserve the backend API contract already established for Today, training plans, recommendations, conversations, and integrations. This change is frontend-only; provider listing may use frontend fixture state until a read API exists, but the UI must be shaped around the existing `POST /api/v1/integrations/connections` binding contract.

## Goals / Non-Goals

**Goals:**

- Replace the placeholder frontend with a Chinese-first Johnny product shell.
- Map `DESIGN.md` tokens into runtime CSS custom properties in `frontend/src/styles.css`.
- Implement reusable Vue components for layout, cards, buttons, badges, evidence rows, recommendation actions, and provider cards.
- Implement Today using the `decision strip` structure: signal, evidence, recommendation, decision.
- Implement Calendar as a readable week/list schedule, not a dense month grid.
- Add a `資料來源` navigation entry and provider-binding guidance for Garmin, Apple Health, Strava, and future providers.
- Cover loading, empty, sparse-data, error, success, busy, and mobile states in component tests.

**Non-Goals:**

- No backend route changes.
- No production OAuth or provider credential flow beyond the current connection request shape.
- No full Agent Inbox or Conversation implementation; labels may appear in navigation, but their complete workflows remain governed by `12-frontend-conversation-inbox`.
- No marketing landing page.
- No visual direction outside `DESIGN.md`.

## Decisions

1. **Use `DESIGN.md` as the visual source of truth.**

   Runtime CSS variables will mirror the token names from `DESIGN.md`, such as `--color-track-night`, `--color-lane-chalk`, and `--font-data`. Components must consume semantic classes or CSS variables rather than hardcoded hex values. This keeps future visual changes centralized.

   Alternative considered: style each Vue component directly from local CSS. Rejected because it would quickly drift from the approved design system.

2. **Build a top navigation shell first.**

   The first stable version will use a top nav with `今日`, `課表`, `Agent 收件匣`, `對話`, and `資料來源`. This matches the current app scale and keeps Today content dominant. A sidebar can be introduced later if Inbox and Conversation become denser.

   Alternative considered: persistent left sidebar. Rejected for now because it competes with the Today cockpit on laptop widths and adds complexity before the product has enough routes.

3. **Represent Today as a decision cockpit, not a dashboard grid.**

   The information order must answer: race context, recovery signal, workout, Johnny recommendation, evidence, decision action. The recommendation card gets the strongest visual treatment with the `decision strip` pattern. Recovery and evidence stay close to the recommendation.

   Alternative considered: equal-weight metric cards. Rejected because the product goal is a daily training decision, not metric browsing.

4. **Use Chinese-first copy with stable action vocabulary.**

   Recommendation actions must use `接受調整`, `編輯調整`, `保留原課表`, and `討論原因` across Today and any linked recommendation card. Provider and platform names stay in their official English forms.

   Alternative considered: mixed English route labels and action labels. Rejected because the MVP product direction is `zh-TW` first.

5. **Make provider binding visible from sparse-data states.**

   Today empty and unavailable-signal states must guide the user to `資料來源`. The provider page should show provider cards, connection status, missing signal coverage, and the privacy boundary that Johnny stores credential references, not raw credentials.

   Alternative considered: bury provider binding in settings. Rejected because synced data quality directly affects recommendation trust.

6. **Use fixture-backed provider display until a list endpoint exists.**

   The current backend has `POST /api/v1/integrations/connections` but no `GET /api/v1/integrations/connections`. The UI can render supported provider cards from local constants and submit connections through the existing API. Existing connection read state should be mockable/testable until a read route is added by a later backend change.

   Alternative considered: block provider UI until a list endpoint exists. Rejected because users still need to understand what data sources Johnny expects.

## Risks / Trade-offs

- **Risk: Visual implementation drifts from `DESIGN.md`.** → Mitigation: add CSS variables named from the design tokens and verify no component introduces duplicate raw palette values.
- **Risk: Calendar becomes too dense on mobile.** → Mitigation: implement a list-first responsive schedule and defer month-grid interactions.
- **Risk: Provider cards imply full OAuth support.** → Mitigation: copy must say `連接資料來源` and reflect MVP connection state without promising unsupported provider auth flows.
- **Risk: Chinese IME behavior breaks conversation or provider forms later.** → Mitigation: shared form controls and tests must account for composition events before any Enter-to-submit behavior ships.
- **Risk: Recommendation trust drops if unavailable signals are hidden.** → Mitigation: Today must explicitly show unavailable signals and a route to `資料來源`.

