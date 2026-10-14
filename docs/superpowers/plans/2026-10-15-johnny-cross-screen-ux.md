# Johnny Cross-Screen UX Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give runners a clear Today workout decision in the selected Morning Start Line visual language and Split Board structure, consistently across every public screen.

**Architecture:** Keep existing Vue data loading, API contracts, and actions in `App.vue`; change their presentation and ordering in small screen-level slices. Centralize visual tokens and shared layout rules in `DESIGN.md` and `styles.css`; keep existing focused components responsible for advice, provider actions, dialogs, and session reviews.

**Tech Stack:** Vue 3, TypeScript, Vite, Vitest, Vue Test Utils, CSS.

**Spec:** [Approved cross-screen UX brief, GitHub issue #14](https://github.com/samfang9527/Johnny/issues/14). Issues are the repository's canonical spec location per `docs/agents/issue-tracker.md`.

## Global Constraints

- Preserve current API contracts, plan generation, Recommendation approval, privacy boundaries, and hidden Conversation.
- Use the five labels `今日`, `計畫`, `Johnny`, `運動員`, `資料`; desktop rail and narrow-screen bottom navigation.
- Use light mint, white, deep green, amber Adjust, blue Rest, and red error/danger from `DESIGN.md`; status always includes text.
- Daily Advice is read-only execution guidance. Only Recommendations offer plan-change approval.
- Do not introduce a readiness score, workout tracking/start action, medical-clearance claim, or automatic plan approval.
- Use the athlete's timezone and unit preference for relevant dates, distances, paces, and sync times.

## File Map

- `DESIGN.md`: reconcile the older cockpit/card guidance and misleading action examples with the approved split structure and truthful destinations.
- `frontend/src/styles.css`: own tokens, desktop rail, bottom navigation, split board, page hierarchy, responsive rules, stable busy states, and focus/contrast treatment. Remove superseded selectors as each screen changes; do not append a third override layer.
- `frontend/src/App.vue`: own public screen order, state presentation, navigation, and existing event wiring. Keep data derivation and modal flows intact.
- `frontend/src/types.ts`: extend `TodayDecisionState`/`TodayDecision` only where the completed state and truthful action label require it.
- `frontend/src/components/DailyAdviceCard.vue`: optional collapsed reading detail on Today while preserving the full read-only view on Johnny.
- `frontend/src/components/ProviderCard.vue`: provider status, source, gaps, and recovery-step copy.
- `frontend/src/App.test.ts`, `frontend/src/Stage7.test.ts`, `frontend/src/components/DailyAdviceCard.test.ts`: behavioral and state regressions. Existing race, session review, and regeneration suites remain gates.

## Review Focus

1. Athlete-local midnight during an open Today/Plan view: the date and selected workout advance together; pin in Task 2, retain `Stage7.test.ts` rollover tests.
2. `completed` Daily Advice: show completion as its own state and never label it Rest; pin in Task 2.
3. No race, no plan, or no connected provider: show useful context and the correct recovery path without demo data; pin in Tasks 3, 4, and 7.
4. A pending Recommendation while Daily Advice says `ease_off`: guidance cannot approve or silently change a Plan Version; pin in Tasks 2 and 5.
5. A 320px viewport, long Traditional Chinese labels, and a safe-area inset: no clipped action or bottom-nav overlap; verify viewport geometry in Task 8.

---

### Task 1: Shared visual system and public navigation

**Files:** Modify `DESIGN.md`, `frontend/src/App.vue:2824-2850`, `frontend/src/styles.css:1-170,2584-2766`; test `frontend/src/App.test.ts`.

**Interfaces:** Keep `navItems: Array<{ key: ViewKey; label: string }>` and `showView(view: ViewKey)`; add no route or API.

- [ ] **Step 1: Write failing tests** named `shows five public destinations with current-page semantics` and `keeps Conversation out of public navigation`: `expect(navButtons).toHaveLength(5)`, `expect(active.attributes('aria-current')).toBe('page')`, and `expect(wrapper.find('[data-view="conversation"]').exists()).toBe(false)`; click Plan and assert its current marker.
- [ ] **Step 2: Run** `npm --prefix frontend test -- src/App.test.ts`; confirm the new active-page assertion fails.
- [ ] **Step 3: Implement** a compact desktop rail, fixed five-item mobile bar, page content clearance, and one shared page-heading/status/row vocabulary. Update `DESIGN.md` layout and Today action examples to match issue #14; delete conflicting old mobile navigation rules.
- [ ] **Step 4: Run** `npm --prefix frontend test -- src/App.test.ts`, `npm --prefix frontend run verify:tokens`, and `npm --prefix frontend run build`; expect pass. Commit these files.

### Task 2: Today decision/workout split

**Files:** Modify `frontend/src/App.vue:399-401,510-580,946-958,2852-2975`, `frontend/src/types.ts:307-316`, `frontend/src/styles.css`; test `frontend/src/App.test.ts`, `frontend/src/Stage7.test.ts`.

**Interfaces:** Keep `todayDecision`, `todayWorkout`, `dailyAdvice`, `todayIsoDate`, and `openWorkoutDetails(workout: WorkoutSummary)`; use `showView('plan' | 'johnny' | 'data')` for destinations. `TodayDecision.state` gains `completed`; `actionLabel` names the actual destination.

- [ ] **Step 1: Write failing tests** named `pairs decision with one workout summary before evidence`, `labels Today action by its real destination`, and `shows completed separately from rest`. Assert `expect(board.findAll('[data-today-workout-summary]')).toHaveLength(1)`, `expect(action.text()).toBe('查看課表細節')` when it opens the modal, fallback `查看計畫`, `expect(completed.attributes('data-decision-state')).toBe('completed')`, and no approval controls. In `Stage7.test.ts`, assert the displayed date strip advances with the selected workout after athlete-local midnight.
- [ ] **Step 2: Run** `npm --prefix frontend test -- src/App.test.ts src/Stage7.test.ts`; confirm the new assertions fail.
- [ ] **Step 3: Implement** the compact date/Plan Week strip and decision/workout pair. Move duplicated workout facts out of the decision side. Make freshness visible, keep planned versus completed facts distinct, and replace the `開始跑步` label without adding tracking. Retain the existing workout detail modal and plan fallback.
- [ ] **Step 4: Run** `npm --prefix frontend test -- src/App.test.ts src/Stage7.test.ts` and `npm --prefix frontend run build`; expect pass. Commit.

### Task 3: Today evidence, advice, and supporting content

**Files:** Modify `frontend/src/App.vue:2977-3040`, `frontend/src/components/DailyAdviceCard.vue`, `frontend/src/styles.css`; test `frontend/src/App.test.ts`, `frontend/src/components/DailyAdviceCard.test.ts`.

**Interfaces:** Add `collapsed?: boolean` to `DailyAdviceCard`; default `false` preserves Johnny's full view. Today passes `collapsed` and uses native disclosure behavior for reading detail.

- [ ] **Step 1: Write failing tests** named `shows two or three evidence rows without duplicate recovery summary`, `keeps stale advice time inside expandable detail`, and `routes no-plan and source failure to Plan or Data`. Assert `expect(today.findAll('[data-today-evidence]')).toHaveLength(1)`, `expect(rows.length).toBeLessThanOrEqual(3)`, stale disclosure contains `先前產生`, and no-plan/source-error actions reach Plan/Data. Retain advice's no-approval assertion.
- [ ] **Step 2: Run** `npm --prefix frontend test -- src/App.test.ts src/components/DailyAdviceCard.test.ts`; confirm new failures.
- [ ] **Step 3: Implement** evidence directly after the split, then expandable Daily Advice; follow with weekly rhythm, session reviews, upcoming/race context when present, and a compact pending-Recommendation nudge. Remove redundant recommendation/recovery cards and unsupported race claims for race-free athletes. Keep loading, empty, stale, and failure messages actionable.
- [ ] **Step 4: Run** `npm --prefix frontend test -- src/App.test.ts src/components/DailyAdviceCard.test.ts` and `npm --prefix frontend run build`; expect pass. Commit.

### Task 4: Plan hierarchy

**Files:** Modify `frontend/src/App.vue:3043-3241`, `frontend/src/styles.css`; test `frontend/src/App.test.ts`, `frontend/src/Stage7.test.ts`, `frontend/src/RaceManagement.test.ts`.

**Interfaces:** Reuse `activePlan`, `currentPlanPhase`, `recoveryWindow`, `visibleScheduleWorkouts`, and existing race/regeneration handlers; no plan computation changes.

- [ ] **Step 1: Write failing tests** named `leads Plan with phase week and next workout` and `keeps active schedule visible during regeneration`. Assert `expect(summaryIndex).toBeLessThan(journeyIndex)`, `expect(journeyIndex).toBeLessThan(raceControlsIndex)`, and the in-flight state still contains the prior workout ID and `目前課表會繼續保留`. Keep the no-race/no-plan fixture case.
- [ ] **Step 2: Run** `npm --prefix frontend test -- src/App.test.ts src/Stage7.test.ts src/RaceManagement.test.ts`; confirm the new hierarchy assertion fails.
- [ ] **Step 3: Implement** the Plan summary, journey, and schedule as the primary flow; group race goals, assessment, and regeneration as secondary actions. Distinguish Recovery Window from Plan Phase and in-flight regeneration from an Active Projection in visible text.
- [ ] **Step 4: Run** `npm --prefix frontend test -- src/App.test.ts src/Stage7.test.ts src/RaceManagement.test.ts` and `npm --prefix frontend run build`; expect pass. Commit.

### Task 5: Johnny pending-decision queue

**Files:** Modify `frontend/src/App.vue:3243-3347`, `frontend/src/styles.css`; test `frontend/src/App.test.ts`.

**Interfaces:** Keep `pendingInboxItems`, `historicalInboxItems`, `RecommendationActions` events, and `DailyAdviceCard` read-only semantics.

- [ ] **Step 1: Write failing tests** named `places pending Recommendations before Daily Advice`, `shows proposed change and evidence before approval`, and `keeps history and weekly review visible when pending is empty`. Assert `expect(pendingIndex).toBeLessThan(adviceIndex)`, pending count equals card count, and `expect(advice.find('[data-testid="recommendation-actions"]').exists()).toBe(false)`; retain history/weekly review and hidden Conversation assertions.
- [ ] **Step 2: Run** `npm --prefix frontend test -- src/App.test.ts`; confirm new order assertion fails.
- [ ] **Step 3: Implement** the pending-first page, quieter history, and read-only advice below pending work. Preserve existing accept/keep states and confirmation behavior; show current plan context before approval only when it can be tied to the proposal reliably.
- [ ] **Step 4: Run** `npm --prefix frontend test -- src/App.test.ts` and `npm --prefix frontend run build`; expect pass. Commit.

### Task 6: Athlete Baseline and settings

**Files:** Modify `frontend/src/App.vue:3472-3679`, `frontend/src/styles.css`; test `frontend/src/App.test.ts`.

**Interfaces:** Keep `athleteBaselineSnapshot`, `athleteSettings`, `submitAthleteSettings()`, and existing canonical-km save payload.

- [ ] **Step 1: Write failing tests** named `groups Athlete fields by training preferences targets and injury` and `keeps target source and save feedback visible`. Assert `expect(baselineIndex).toBeLessThan(formIndex)`, fieldset legends name training, preferences, targets, and injury, `expect(form.findAll('button[type="submit"]')).toHaveLength(1)`, and existing inline error/source assertions still pass.
- [ ] **Step 2: Run** `npm --prefix frontend test -- src/App.test.ts`; confirm new grouping assertion fails.
- [ ] **Step 3: Implement** the Baseline-led layout and form grouping without changing fields, conversion, validation, or persistence. Keep recent metrics sourced and private Athlete Memory absent.
- [ ] **Step 4: Run** `npm --prefix frontend test -- src/App.test.ts` and `npm --prefix frontend run build`; expect pass. Commit.

### Task 7: Data coverage and provider repair

**Files:** Modify `frontend/src/App.vue:3681-3779`, `frontend/src/components/ProviderCard.vue`, `frontend/src/styles.css`; test `frontend/src/App.test.ts`.

**Interfaces:** Keep `signalCoverage: SignalCoverageItem[]`, provider connection/sync/disconnect events, and masked credential form.

- [ ] **Step 1: Write failing tests** named `labels each signal as available or missing with its source` and `names provider sync failure and next action`. Assert `expect(signalRows).toHaveLength(6)`, each row contains source and `已取得` or `待補`, and reauth/partial failure rows contain an actionable recovery label; `expect(wrapper.text()).not.toContain(secret)`. Retain the disconnected-provider case.
- [ ] **Step 2: Run** `npm --prefix frontend test -- src/App.test.ts`; confirm new signal-status assertion fails.
- [ ] **Step 3: Implement** a coverage-first page with aligned signal rows and provider details underneath. Make last successful sync and resource gaps readable; keep existing connect, sync, and disconnect flows and masked fields.
- [ ] **Step 4: Run** `npm --prefix frontend test -- src/App.test.ts` and `npm --prefix frontend run build`; expect pass. Commit.

### Task 8: Authentication and cross-screen verification

**Files:** Modify `frontend/src/App.vue:2753-2823`, `frontend/src/styles.css`; test `frontend/src/App.test.ts`.

**Interfaces:** Keep Email/Google auth handlers, `authMode`, session checks, and current field names/autocomplete.

- [ ] **Step 1: Write failing tests** named `keeps login and signup states in the shared visual system` and `announces session expiry and auth errors next to the relevant action`. Assert `expect(login.find('.auth-panel .page-heading').exists()).toBe(true)`, `expect(login.find('[name="displayName"]').exists()).toBe(false)`, signup reveals it, Email/Google paths remain, and `expect(error.attributes('role')).toBe('alert')`. Retain password autocomplete/paste tests.
- [ ] **Step 2: Run** `npm --prefix frontend test -- src/App.test.ts`; confirm the new assertions fail.
- [ ] **Step 3: Implement** matching auth layout and precise error/busy copy. At 320px and desktop widths, inspect every public screen plus auth for order, focus, contrast, long text, and safe-area clearance; fix issues found.
- [ ] **Step 4: Run** `npm --prefix frontend test`, `npm --prefix frontend run build`, and `npm --prefix frontend run verify:tokens`; expect pass. In browser review of every public screen and auth, verify `document.documentElement.scrollWidth <= innerWidth` and that focused controls/actions remain above the bottom bar at 320px with a safe-area inset. Check Today decision states, keyboard flow, and desktop split; commit.
