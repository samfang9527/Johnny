## Why

`11-frontend-today-calendar` defines the functional Today and calendar scope, but it does not yet lock the visual language, Chinese-first copy, or provider-binding entry points needed for Johnny to feel like a product rather than a starter Vue shell. `DESIGN.md` now establishes Johnny's product identity, so the frontend change should explicitly implement that system from the first real screen.

## What Changes

- Apply the `DESIGN.md` visual system to the Today and Calendar frontend surfaces.
- Replace the scaffold UI with a Chinese-first Johnny app shell using `今日`, `課表`, `Agent 收件匣`, `對話`, and `資料來源` navigation labels.
- Introduce reusable visual primitives for cards, buttons, status badges, evidence rows, recommendation actions, and provider cards.
- Add a Today layout that presents race countdown, recovery evidence, today's workout, current recommendation, unavailable signals, and decision actions through the `decision strip` pattern.
- Add a calendar-oriented workout schedule view that prioritizes week/list readability over dense month-grid browsing.
- Add a first-class `資料來源` entry point and sparse-data guidance so users can bind Garmin, Apple Health, Strava, or future providers when Today lacks training or recovery signals.
- Preserve the backend API contract from `11-frontend-today-calendar`; no backend behavior is changed by this proposal.

## Capabilities

### New Capabilities

- `frontend-today-visual-design`: Covers the Chinese-first Johnny visual system application for Today, Calendar, recommendation decisions, recovery evidence, and provider-binding entry points.

### Modified Capabilities

None.

## Impact

- Frontend Vue/Vite/TypeScript app shell, styles, components, composables, and tests.
- `frontend/src/styles.css` will become the runtime token owner mapped from `DESIGN.md`.
- Today and Calendar component tests must verify Chinese labels, stable loading/empty/error states, recommendation action labels, and provider-binding guidance.
- No backend API, persistence schema, or domain model changes are required for this visual design change.
