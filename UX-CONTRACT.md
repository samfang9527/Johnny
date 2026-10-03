# Johnny UX Contract

## Canonical UI Map

| Capability | Canonical owner | Source of truth | Allowed variants | Verification |
|---|---|---|---|---|
| Date | Authored `DatePicker` component in `frontend/src/components/DatePicker.vue` with strict `YYYY-MM-DD` typed input | `premium-ui.json` ownership and `DESIGN.md` layout/form guidance | authored + typed | component test, build, premium audit |
| Select/Listbox | Native select in `frontend/src/App.vue` Garmin region and athlete settings forms | `premium-ui.json` ownership and `DESIGN.md` layout/form guidance | native | component test, build, premium audit |
| Form | App-owned Vue form markup with `novalidate` and inline validation | `frontend/src/App.vue`, `DESIGN.md` Forms and overlays | provider binding, race entry, athlete settings, hidden conversation composer | component test, premium audit |
| Confirmation Dialog | Reusable `ConfirmDialog` component in `frontend/src/components/ConfirmDialog.vue` | `DESIGN.md` Forms and overlays | discard confirmation, provider disconnect | component test, premium audit |
| Scrollbar | Global application stylesheet in `frontend/src/styles.css` | `DESIGN.md` token mapping and CSS custom properties | global baseline | token verifier, premium audit |
| Button | Reusable `AppButton` component in `frontend/src/components/AppButton.vue` | `DESIGN.md` Components | primary, neutral, warning, danger | component test, build |

## Workflow Rules

- Production navigation shows exactly `今日`, `計畫`, `Johnny`, `運動員`, and `資料`.
- Conversation remains hidden from production navigation while the code path is retained for later reactivation and tests.
- `今日` is the default route and acts as the start-line cockpit.
- `今日` starts with a Today Decision card before schedule, plan, or recommendation details.
- Today Decision states use:
  - `我可以` with primary action `開始跑步`
  - `不太對勁` with primary action `接受調整`
  - `先收一下` with primary action `記錄休息`
- Today Decision evidence shows the top current training/recovery signals plus one subtle Athlete Memory insight when relevant. It does not expose Athlete Memory as a browsable data object.
- `今日` mobile layout uses a centered vertical flow. Desktop uses the main Today decision column plus a right-side context rail for race, plan, signal coverage, and pending recommendation context.
- `今日` includes a weekly activity rhythm chart below the decision card.
- `計畫` owns an inclusive training journey with phase segments at the top and weekly schedule underneath. Races are optional goals inside the journey, not a required identity for every athlete.
- `Johnny` owns pending recommendation decisions first, weekly review/check-ins below, and no public conversation composer for this release.
- Johnny recommendation cards may display the emotional state language, but decision buttons use formal action language.
- `運動員` owns Athlete Baseline. It shows a baseline snapshot first: weekly mileage, experience, injury status, preferred training rhythm, and recent baseline metrics. Editable profile/settings remain below the snapshot.
- Athlete Memory is Johnny's private working context and must not appear as a standalone navigation item, page, table, or browsable list. It may surface only as contextual explanation copy in recommendations or future conversation.
- `資料` starts with Signal Coverage: activity, sleep, HRV, resting heart rate, training load, and athlete baseline. Provider connection cards and sync details appear below.
- `運動員` saves through `PUT /api/v1/athlete/profile`, displays weekly mileage in the selected unit, sends canonical `current_weekly_mileage_km`, exposes only the typed threshold-pace setting from otherwise hidden `training_preferences`, and validates structured injury fields before submit.
- `運動員` timezone uses the canonical native select pattern with a fixed common-timezone list; valid existing profile timezones outside the list are preserved as a temporary current option.
- `計畫` keeps race-goal creation through `POST /api/v1/races`; the create UI accepts kilometers and converts to API `distance_meters`, requires a product priority (`主要目標`, `次要目標`, `暖身賽`), and never sends race status on create.
- The calendar hydrates from `GET /api/v1/races` for the active six-month window. Workout lists remain supporting execution context.

## Route Document Title Policy

- Client-side view changes update `document.title` to `{Page} — Johnny`.
- Page names follow the production navigation vocabulary: `今日`, `計畫`, `Johnny`, `運動員`, `資料`.
- Loading and error states keep the same page title and expose the state in-page rather than leaving stale content.

## Visual State Rules

- Run / Adjust / Rest have distinct visual tones, but preserve the same card structure so users do not relearn the page.
- Busy buttons keep stable dimensions.
- Empty, loading, and error states keep the same page footprint where possible.
- Important values wrap instead of clipping on narrow viewports.
- No product flow calls browser-native `alert()`, `confirm()`, or `prompt()`.
