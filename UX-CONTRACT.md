# Johnny UX Contract

## Canonical UI Map

| Capability | Canonical owner | Source of truth | Allowed variants | Verification |
|---|---|---|---|---|
| Date | Authored `DatePicker` component in `frontend/src/components/DatePicker.vue` with strict `YYYY-MM-DD` typed input | `premium-ui.json` ownership and `DESIGN.md` layout/form guidance | authored + typed | component test, build, premium audit |
| Select/Listbox | Native select in `frontend/src/App.vue` Garmin region and athlete settings forms | `premium-ui.json` ownership and `DESIGN.md` layout/form guidance | native | component test, build, premium audit |
| Form | App-owned Vue form markup with `novalidate` and inline validation | `frontend/src/App.vue`, `DESIGN.md` Forms and overlays | provider binding, race entry, athlete settings, hidden conversation composer | component test, premium audit |
| Confirmation Dialog | Reusable `ConfirmDialog` component in `frontend/src/components/ConfirmDialog.vue` | `DESIGN.md` Forms and overlays | discard confirmation, provider disconnect, race deletion | component test, premium audit |
| Scrollbar | Global application stylesheet in `frontend/src/styles.css` | `DESIGN.md` token mapping and CSS custom properties | global baseline | token verifier, premium audit |
| Button | Reusable `AppButton` component in `frontend/src/components/AppButton.vue` | `DESIGN.md` Components | primary, neutral, warning, danger | component test, build |

## Workflow Rules

- Production navigation shows exactly `今日`, `計畫`, `Johnny`, `運動員`, and `資料`.
- Conversation remains hidden from production navigation while the code path is retained for later reactivation and tests.
- `今日` is the default route and acts as the start-line cockpit.
- `今日` starts with its title, athlete-local date, an upcoming-race line when available, and a seven-day schedule strip. Today's date is marked. The decision and actual workout share one ruled Split Board below the strip, followed on the same surface by evidence and the plan/next-workout/pending footer.
- Today Decision states use:
  - `我可以` with an action to workout details when available, otherwise `查看計畫`; Johnny does not yet track a run
  - `不太對勁` or `先收一下` with primary action `查看 Johnny 建議` when current Daily Advice exists
  - `不太對勁` or `先收一下` with primary action `查看待決定建議` when a pending Recommendation exists without current Daily Advice
  - `不太對勁` or `先收一下` with primary action `查看課表` when neither exists
- When a ready Daily Advice exists, Today Decision follows its validated `follow_plan`, `ease_off`, `rest`, or `completed` mode. Advice is read-only: `ease_off`, `rest`, and `completed` link to the advice without an acceptance action. Pending or stale advice uses a conservative fallback.
- Today and Johnny may show the same current Daily Advice for the athlete-local date, with all three sections, generation time, and freshness. They never show two revisions together. Pending approval-backed Recommendations remain separate in Johnny and retain their actions.
- Manual Garmin sync completion may return a Daily Advice run. The frontend observes that run and refreshes Today when it completes; a failed refresh retains prior advice with stale status.
- Today Decision evidence shows the top current training/recovery signals plus one subtle Athlete Memory insight when relevant. It does not expose Athlete Memory as a browsable data object.
- `今日` mobile layout retains the seven-day strip and stacks the decision, workout, evidence, and footer in that order. Desktop uses one two-column decision/workout plane, a one-pixel vertical rule, aligned evidence rows, and a ruled footer. Pending recommendations appear in the footer; other secondary context follows below.
- The schedule strip uses current Plan Week dates when a valid Plan Week is available, otherwise the athlete-local calendar week. It shows scheduled workouts from the active Plan Version, and never treats past activity bars as scheduled sessions. Without an effective schedule, unassigned dates read `待排` rather than `休`.
- All dates in Today's strip are keyboard-reachable buttons, and today remains visually marked. Selecting another day opens an inline preview beneath the strip with its workout or truthful rest/pending state. Selecting another day updates that preview; selecting the same day or today closes it and returns to the initial Today view. An explicit `查看完整計畫` action opens `計畫`. Today's date-specific decision and advice remain tied to today.
- Controls acknowledge hover, press, and selection promptly. The Today preview, expandable sections, and dialogs use short open/close motion while preserving native keyboard and focus behavior; reduced-motion preferences remove the spatial movement. Navigation between top-level pages remains immediate.
- The optional next-race line appears before the strip and shows the saved upcoming race's name, distance, date and athlete-local countdown. It never shows a fabricated finish goal or implies the race is included in the active Plan Version; the former lower race card is not repeated.
- `今日` uses the seven-day schedule strip for the weekly view. It does not show sample activity history as real athlete data; session reviews remain below the decision board.
- `計畫` starts with one `目前計畫` section containing the current phase, week and next workout, and the training journey; the weekly schedule follows. A native disclosure shows only races snapshotted into the active plan as included races, distinguishing its target race from supporting races. Saved goals and regeneration actions remain available inside the disclosure; a no-plan state exposes plan generation directly. There is no separate `階段詳情` section. Races are optional goals, not a required identity for every athlete.
- `Johnny` owns pending recommendation decisions first, weekly review/check-ins below, and no public conversation composer for this release.
- Johnny recommendation cards may display the emotional state language, but decision buttons use formal action language.
- `運動員` owns Athlete Baseline. It shows a baseline snapshot first: weekly mileage, experience, injury status, preferred training rhythm, and recent baseline metrics. Editable profile/settings remain below the snapshot.
- Athlete Memory is Johnny's private working context and must not appear as a standalone navigation item, page, table, or browsable list. It may surface only as contextual explanation copy in recommendations or future conversation.
- `資料` starts with Signal Coverage: activity, sleep, HRV, resting heart rate, training load, and athlete baseline. Provider connection cards and sync details appear below.
- `運動員` saves through `PUT /api/v1/athlete/profile`, displays weekly mileage in the selected unit, sends canonical `current_weekly_mileage_km`, exposes only the typed threshold-pace setting from otherwise hidden `training_preferences`, and validates structured injury fields before submit.
- Training targets use backend-resolved evidence. Athlete settings offer Garmin automatic threshold pace or an optional manual override; a saved manual value keeps precedence until the athlete selects Garmin and saves. Resting/max HR inputs are removed; Garmin running zones (general zones when no valid running profile exists) supply HR ranges.
- Garmin evidence shows source, last successful sync, threshold measurement date when available, and stale/unavailable status. Failed or empty syncs retain last-good values. Disconnect clears provider evidence from current target resolution while preserving imported history.
- Today, plan rows, and workout details show RPE plus available estimated pace/HR ranges. Upcoming planned workouts resolve current evidence without plan regeneration; completed and past workouts retain their saved targets. Saving settings, completing sync, or disconnecting refreshes the displayed workouts.
- `運動員` timezone uses the canonical native select pattern with a fixed common-timezone list; valid existing profile timezones outside the list are preserved as a temporary current option.
- `計畫` keeps race-goal creation through `POST /api/v1/races`; the create UI accepts kilometers and converts to API `distance_meters`, requires a product priority (`主要目標`, `次要目標`, `暖身賽`), and never sends race status on create.
- The calendar hydrates from `GET /api/v1/races` for the active six-month window. Workout lists remain supporting execution context.

## Route Document Title Policy

- Client-side view changes update `document.title` to `{Page} — Johnny`.
- Page names follow the production navigation vocabulary: `今日`, `計畫`, `Johnny`, `運動員`, `資料`.
- Loading and error states keep the same page title and expose the state in-page rather than leaving stale content.

## Visual State Rules

- Run / Adjust / Rest have distinct headline tones while preserving the same continuous Split Board structure so users do not relearn the page.
- Busy buttons keep stable dimensions.
- Empty, loading, and error states keep the same page footprint where possible.
- Important values wrap instead of clipping on narrow viewports.
- No product flow calls browser-native `alert()`, `confirm()`, or `prompt()`.

## Target race management

- Race editing reuses `RaceGoalModal` and loads the current values from the race detail API; unchanged optional values retain their saved precision. Unsaved edits require a discard confirmation.
- Race deletion uses `ConfirmDialog`, names the target, and explains that plans and workouts are retained. The owner-scoped race API detaches linked plan versions before removing the race.
- Saves and deletes disable duplicate submission, retain user input or the confirmation on failure, and refresh race and training displays on success. Adding, moving, editing, cancelling, or deleting any race in the active projection's remaining date range shows a manual regeneration reminder; a saved race is not shown as part of the current workout plan until regeneration succeeds.
- `useModalFocus` owns focus, Escape, background isolation, and scroll restoration for the race form and shared confirmation dialog, including nested discard confirmations.

### Activity session review

- Running, track running, and trail running share completion and load classification. Trail pace is excluded from road pace evidence.
- Same-local-day running recordings form a candidate session only when recordings do not overlap and consecutive end-to-start gaps are at most 30 minutes. Active totals exclude gaps; original recordings remain intact.
- One clear session and one running workout on its date are automatically matched and count as one completed workout. Ambiguous matches ask for review and do not establish a missed workout. Activity volume always counts.
- Today shows automatic match confirmation cards with original recordings and editable collapsed history. Athletes can confirm, choose a workout, split recordings, or mark them unplanned. Explicit decisions survive sync; a partial or changed-membership group save is rejected and must be reloaded.
- Today and the session review API allow pairing decisions only for the athlete's latest seven local dates, including today. Older decisions remain saved but cannot be changed.
- Saving a decision queues affected Daily Advice refreshes and marks older advice stale immediately. Confirmation is optional for clear automatic matches. The advice card exposes the evidence cutoff timestamp.
