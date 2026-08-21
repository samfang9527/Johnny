## 1. Design Gate and Token Setup

- [x] 1.1 Review `openspec/changes/frontend-today-visual-design/design.md` with the product owner and receive explicit approval before implementation.
- [x] 1.2 Map `DESIGN.md` color, typography, radius, spacing, and component tokens into `frontend/src/styles.css` CSS custom properties.
- [x] 1.3 Add global product UI baselines for Chinese-first typography, visible focus states, stable scrollbars, button states, loading states, and reduced-motion behavior.
- [x] 1.4 Add a token drift check or source search to verify Johnny palette values are centralized in the stylesheet rather than duplicated in Vue components.

## 2. App Shell and Shared Primitives

- [x] 2.1 Replace the starter Vue shell with a Johnny product shell using navigation labels `今日`, `課表`, `Agent 收件匣`, `對話`, and `資料來源`.
- [x] 2.2 Implement shared visual primitives for cards, buttons, status badges, loading panels, empty states, error states, and section headings.
- [x] 2.3 Implement shared evidence row/list components using the `DESIGN.md` data typography and unavailable-signal presentation.
- [x] 2.4 Implement shared recommendation action controls with stable labels `接受調整`, `編輯調整`, `保留原課表`, and `討論原因`.

## 3. Today Decision Cockpit

- [x] 3.1 Define typed frontend models and fixtures for Today context, race summary, recovery evidence, scheduled workouts, unavailable signals, and current recommendation.
- [x] 3.2 Implement the Today view layout with race countdown, recovery signals, today's workout, recommendation summary, evidence, unavailable signals, and action controls.
- [x] 3.3 Implement the `decision strip` visual treatment for pending recommendations with stable desktop and mobile layouts.
- [x] 3.4 Wire recommendation accept, reject, edit placeholder, and discuss placeholder actions to existing API/client boundaries where available.
- [x] 3.5 Add Today loading, error, empty, sparse-data, full-data, and busy-action component tests.

## 4. Calendar Schedule

- [x] 4.1 Define typed frontend models and fixtures for planned workouts grouped by scheduled date.
- [x] 4.2 Implement the `課表` view as a week/list-oriented schedule with workout type, purpose, distance or duration, pace or heart-rate guidance, and status.
- [x] 4.3 Add responsive behavior that preserves workout details and actions on narrow viewports without clipping long Chinese text.
- [x] 4.4 Add calendar schedule tests for loaded, empty, status, and narrow-layout-safe rendering.

## 5. Data Sources

- [x] 5.1 Define supported provider metadata for Garmin, Apple Health, Strava, and future disabled providers, including signal coverage and status copy.
- [x] 5.2 Implement the `資料來源` surface with provider cards, connection status, missing-signal guidance, and `連接資料來源` actions.
- [x] 5.3 Implement the MVP provider binding form against `POST /api/v1/integrations/connections`, preserving the credential-reference privacy boundary in UI copy.
- [x] 5.4 Add tests for provider card rendering, unsupported/future provider states, sparse-data navigation from Today to `資料來源`, and successful connection submission.

## 6. Verification

- [x] 6.1 Run OpenSpec validation for `frontend-today-visual-design` and fix all errors.
- [x] 6.2 Run the official `DESIGN.md` linter and the frontend-design-premium strict audit after any token or design-system changes.
- [x] 6.3 Run frontend typecheck/build and all available frontend tests.
- [x] 6.4 Manually inspect the app in a browser at desktop and narrow mobile widths for Chinese text fit, focus states, loading/empty/error geometry, and reduced-motion behavior.
- [x] 6.5 Update task checkboxes only after each item is implemented and verified.
