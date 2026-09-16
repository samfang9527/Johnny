# Johnny Start-Line UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the approved light mint Johnny start-line UI across Today, Plan, Johnny, Athlete, and Data while preserving existing API behavior.

**Architecture:** Keep the current Vue single-app structure, but rename the public view model and split complex display logic into focused helpers/components as needed. `DESIGN.md` remains the visual source of truth and `frontend/src/styles.css` maps the runtime CSS variables. Existing API clients and domain mapping functions stay intact.

**Tech Stack:** Vue 3, TypeScript, Vite, Vitest, Vue Test Utils, CSS custom properties.

**Spec:** `docs/superpowers/specs/2026-09-16-johnny-start-line-ui-design.md`

## Global Constraints

- Production navigation labels are exactly `今日`, `計畫`, `Johnny`, `運動員`, `資料`.
- Conversation remains hidden from production navigation and from the public Johnny page.
- Today Decision states are `我可以`, `不太對勁`, `先收一下`.
- Today Decision actions are `開始跑步`, `接受調整`, `記錄休息`.
- Rest supporting copy may use `今天不要硬撐，跑鞋先放假。`
- Athlete Memory is private Johnny context and must not appear as a standalone page, tab, table, navigation item, or browsable list.
- Signal Coverage counts activity, sleep, HRV, resting heart rate, training load, and athlete baseline.
- Existing API client methods and persistence behavior remain unchanged unless a test proves current wiring is broken.

---

## File Structure

- Modify `frontend/src/types.ts`: add new public view keys and Today Decision helper types.
- Modify `frontend/src/fixtures.ts`: add weekly activity, phase timeline, signal coverage, and baseline snapshot fixture data.
- Modify `frontend/src/App.vue`: update nav, computed display helpers, Today/Plan/Johnny/Athlete/Data markup, and document title handling.
- Modify `frontend/src/styles.css`: map new DESIGN tokens and implement light mint responsive layout.
- Modify `frontend/src/App.test.ts`: update shell tests and add view tests for Today Decision, Plan, Johnny, Athlete, and Data.
- Keep `frontend/src/components/AppButton.vue`: reuse existing busy-state behavior; extend CSS only if needed.
- Keep `frontend/src/components/RecommendationActions.vue`, `ProviderCard.vue`, `RaceGoalModal.vue`, `DatePicker.vue`, and `ConfirmDialog.vue`: reuse existing canonical owners.

---

### Task 1: Public Navigation Model

**Files:**
- Modify: `frontend/src/types.ts`
- Modify: `frontend/src/App.vue`
- Test: `frontend/src/App.test.ts`

**Interfaces:**
- Consumes: existing `ViewKey`.
- Produces: `ViewKey = 'today' | 'plan' | 'johnny' | 'athlete' | 'data' | 'conversation'`; `navItems` with Chinese labels.

- [ ] **Step 1: Write the failing navigation test**

Add this test in `frontend/src/App.test.ts`:

```ts
it('shows the start-line navigation and keeps conversation hidden', () => {
  const wrapper = mount(App)

  const navText = wrapper.get('nav').text()
  expect(navText).toContain('今日')
  expect(navText).toContain('計畫')
  expect(navText).toContain('Johnny')
  expect(navText).toContain('運動員')
  expect(navText).toContain('資料')
  expect(navText).not.toContain('訓練安排')
  expect(navText).not.toContain('Agent 收件匣')
  expect(navText).not.toContain('運動員設定')
  expect(navText).not.toContain('資料來源')
  expect(navText).not.toContain('對話')
})
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npm run test -- App.test.ts -t "start-line navigation"`

Expected: FAIL because old nav labels are still rendered.

- [ ] **Step 3: Update the public view key type**

Change `frontend/src/types.ts`:

```ts
export type ViewKey = 'today' | 'plan' | 'johnny' | 'athlete' | 'data' | 'conversation'
```

- [ ] **Step 4: Update `navItems` and hash compatibility**

In `frontend/src/App.vue`, replace the public nav array with:

```ts
const navItems: Array<{ key: ViewKey; label: string }> = [
  { key: 'today', label: '今日' },
  { key: 'plan', label: '計畫' },
  { key: 'johnny', label: 'Johnny' },
  { key: 'athlete', label: '運動員' },
  { key: 'data', label: '資料' },
]
```

Add a legacy hash mapper near `viewFromHash()`:

```ts
const legacyViewMap: Partial<Record<string, ViewKey>> = {
  calendar: 'plan',
  inbox: 'johnny',
  'athlete-settings': 'athlete',
  sources: 'data',
}
```

Update `viewFromHash()` to map old hashes:

```ts
const rawHashView = window.location.hash.replace('#', '')
const mappedView = legacyViewMap[rawHashView] ?? (rawHashView as ViewKey)
return navItems.some((item) => item.key === mappedView) ? mappedView : undefined
```

- [ ] **Step 5: Update view switching data attributes**

Where nav buttons render `data-view`, set it to the new key:

```vue
:data-view="item.key"
```

- [ ] **Step 6: Run the test**

Run: `cd frontend && npm run test -- App.test.ts -t "start-line navigation"`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/types.ts frontend/src/App.vue frontend/src/App.test.ts
git commit -m "feat: update Johnny navigation model"
```

---

### Task 2: Today Decision Model And Tests

**Files:**
- Modify: `frontend/src/types.ts`
- Modify: `frontend/src/App.vue`
- Modify: `frontend/src/fixtures.ts`
- Test: `frontend/src/App.test.ts`

**Interfaces:**
- Consumes: `RecommendationSummary`, `EvidenceItem`, `WorkoutSummary`.
- Produces: `TodayDecision` with `state`, `label`, `actionLabel`, `tone`, `voice`, `memoryInsight`.

- [ ] **Step 1: Add Today Decision types**

In `frontend/src/types.ts`, add:

```ts
export type TodayDecisionState = 'run' | 'adjust' | 'rest'

export interface TodayDecision {
  state: TodayDecisionState
  label: '我可以' | '不太對勁' | '先收一下'
  actionLabel: '開始跑步' | '接受調整' | '記錄休息'
  tone: 'run' | 'adjust' | 'rest'
  voice: string
  memoryInsight?: string
}
```

- [ ] **Step 2: Add the failing Today Decision test**

Add this test:

```ts
it('renders Today as a Run Adjust Rest decision card with evidence', () => {
  const wrapper = mount(App)

  expect(wrapper.get('[data-testid="today-decision-card"]').text()).toContain('不太對勁')
  expect(wrapper.get('[data-testid="today-decision-card"]').text()).toContain('今天不要硬撐，跑鞋先放假。')
  expect(wrapper.get('[data-testid="today-decision-action"]').text()).toContain('接受調整')
  expect(wrapper.findAll('[data-testid="today-evidence-chip"]').length).toBeGreaterThanOrEqual(3)
  expect(wrapper.text()).toContain('依照你過去的恢復模式')
})
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `cd frontend && npm run test -- App.test.ts -t "Run Adjust Rest decision"`

Expected: FAIL because the decision card and test ids do not exist.

- [ ] **Step 4: Import the new types**

Update the type import in `frontend/src/App.vue` to include:

```ts
TodayDecision,
TodayDecisionState,
```

- [ ] **Step 5: Add decision builder**

Add this function near the existing Today helper functions:

```ts
function buildTodayDecision(recommendation: RecommendationSummary | null, evidence: EvidenceItem[]): TodayDecision {
  const hasDangerEvidence = evidence.some((item) => item.tone === 'danger')
  const hasWarningRecommendation = recommendation?.priority === 'warning' || recommendation?.priority === 'danger'

  if (recommendation && (hasDangerEvidence || recommendation.priority === 'danger')) {
    return {
      state: 'rest',
      label: '先收一下',
      actionLabel: '記錄休息',
      tone: 'rest',
      voice: '今天不要硬撐，跑鞋先放假。',
      memoryInsight: '依照你過去的恢復模式，今天建議保守。',
    }
  }

  if (recommendation && hasWarningRecommendation) {
    return {
      state: 'adjust',
      label: '不太對勁',
      actionLabel: '接受調整',
      tone: 'adjust',
      voice: '今天先穩住節奏，保留訓練目的就好。',
      memoryInsight: '依照你過去的恢復模式，今天建議保守。',
    }
  }

  return {
    state: 'run',
    label: '我可以',
    actionLabel: '開始跑步',
    tone: 'run',
    voice: '狀態可以，照計畫跑，節奏不要偷加。',
  }
}
```

- [ ] **Step 6: Add computed decision**

Add:

```ts
const todayDecision = computed(() => buildTodayDecision(recommendation.value, recoveryEvidence.value))
const todayEvidenceChips = computed(() => recoveryEvidence.value.slice(0, 3))
```

- [ ] **Step 7: Replace the top Today card markup**

In the `activeView === 'today'` section, add a card with this structure before other Today details:

```vue
<article
  class="today-decision-card"
  :class="`today-decision-card--${todayDecision.tone}`"
  data-testid="today-decision-card"
>
  <div class="today-decision-card__header">
    <span class="card-kicker">Johnny 今天看起來</span>
    <strong>{{ todayDecision.label }}</strong>
  </div>
  <p>{{ todayDecision.voice }}</p>
  <div class="today-decision-card__workout">
    <span>{{ todayWorkout.type }}</span>
    <strong>{{ todayWorkout.distance || todayWorkout.duration || '今日訓練' }}</strong>
    <small>{{ todayWorkout.pace || todayWorkout.heartRateZone || todayWorkout.purpose }}</small>
  </div>
  <div class="today-evidence-chip-list" aria-label="今日決策證據">
    <span v-for="item in todayEvidenceChips" :key="`${item.source}-${item.metric}`" class="today-evidence-chip" data-testid="today-evidence-chip">
      <span>{{ item.metric }}</span>
      <strong>{{ item.value }}</strong>
      <small>{{ item.summary }}</small>
    </span>
  </div>
  <p v-if="todayDecision.memoryInsight" class="memory-insight">{{ todayDecision.memoryInsight }}</p>
  <AppButton tone="primary" data-testid="today-decision-action">{{ todayDecision.actionLabel }}</AppButton>
</article>
```

- [ ] **Step 8: Run the Today Decision test**

Run: `cd frontend && npm run test -- App.test.ts -t "Run Adjust Rest decision"`

Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add frontend/src/types.ts frontend/src/App.vue frontend/src/App.test.ts
git commit -m "feat: add Today decision model"
```

---

### Task 3: Weekly Activity Rhythm And Today Context Rail

**Files:**
- Modify: `frontend/src/types.ts`
- Modify: `frontend/src/fixtures.ts`
- Modify: `frontend/src/App.vue`
- Test: `frontend/src/App.test.ts`

**Interfaces:**
- Produces: `WeeklyActivityPoint` fixture data and rendered chart bars/line.
- Consumes: `raceSummary`, `displayInboxItems`, Signal Coverage helper from Task 6 when available.

- [ ] **Step 1: Add type**

In `frontend/src/types.ts`, add:

```ts
export interface WeeklyActivityPoint {
  dayLabel: string
  distanceKm: number
  loadLabel: string
}
```

- [ ] **Step 2: Add fixture**

In `frontend/src/fixtures.ts`, export:

```ts
export const weeklyActivity: WeeklyActivityPoint[] = [
  { dayLabel: '一', distanceKm: 6, loadLabel: 'Easy' },
  { dayLabel: '二', distanceKm: 0, loadLabel: 'Rest' },
  { dayLabel: '三', distanceKm: 8, loadLabel: 'Easy' },
  { dayLabel: '四', distanceKm: 10, loadLabel: 'Tempo' },
  { dayLabel: '五', distanceKm: 0, loadLabel: 'Rest' },
  { dayLabel: '六', distanceKm: 5, loadLabel: 'Easy' },
  { dayLabel: '日', distanceKm: 18, loadLabel: 'Long' },
]
```

Add `WeeklyActivityPoint` to the type import in that file.

- [ ] **Step 3: Add failing test**

```ts
it('shows weekly activity rhythm below the Today decision', () => {
  const wrapper = mount(App)

  expect(wrapper.get('[data-testid="weekly-activity"]').text()).toContain('本週活動')
  expect(wrapper.findAll('[data-testid="weekly-activity-bar"]').length).toBe(7)
})
```

- [ ] **Step 4: Run the test to verify it fails**

Run: `cd frontend && npm run test -- App.test.ts -t "weekly activity rhythm"`

Expected: FAIL because the chart does not exist.

- [ ] **Step 5: Import fixture and render chart**

In `frontend/src/App.vue`, import `weeklyActivity as fixtureWeeklyActivity`.

Add:

```ts
const weeklyActivityPoints = computed(() => fixtureWeeklyActivity)
const maxWeeklyDistance = computed(() => Math.max(...weeklyActivityPoints.value.map((point) => point.distanceKm), 1))
```

Render below the decision card:

```vue
<section class="surface-card weekly-activity" data-testid="weekly-activity" aria-labelledby="weekly-activity-title">
  <div class="section-heading-row">
    <h3 id="weekly-activity-title">本週活動</h3>
    <span>跑量節奏</span>
  </div>
  <div class="weekly-activity__bars" aria-label="本週跑步距離">
    <div v-for="point in weeklyActivityPoints" :key="point.dayLabel" class="weekly-activity__day">
      <span class="weekly-activity__bar" data-testid="weekly-activity-bar" :style="{ '--bar-size': `${Math.round((point.distanceKm / maxWeeklyDistance) * 100)}%` }"></span>
      <strong>{{ point.dayLabel }}</strong>
      <small>{{ point.distanceKm }} km</small>
    </div>
  </div>
</section>
```

- [ ] **Step 6: Add desktop context rail markup**

Inside Today desktop layout, add:

```vue
<aside class="today-context-rail" aria-label="今日脈絡">
  <section class="surface-card">
    <span class="card-kicker">目標賽事</span>
    <strong>{{ raceSummary.name }}</strong>
    <p>{{ raceSummary.daysRemaining }} 天後 · {{ raceSummary.goal }}</p>
  </section>
  <section class="surface-card">
    <span class="card-kicker">Johnny 待決定</span>
    <strong>{{ pendingInboxItems.length }}</strong>
    <p>目前待處理建議</p>
  </section>
</aside>
```

- [ ] **Step 7: Run the test**

Run: `cd frontend && npm run test -- App.test.ts -t "weekly activity rhythm"`

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/types.ts frontend/src/fixtures.ts frontend/src/App.vue frontend/src/App.test.ts
git commit -m "feat: add weekly activity rhythm"
```

---

### Task 4: Plan Journey Timeline

**Files:**
- Modify: `frontend/src/types.ts`
- Modify: `frontend/src/fixtures.ts`
- Modify: `frontend/src/App.vue`
- Test: `frontend/src/App.test.ts`

**Interfaces:**
- Produces: `PlanPhase` fixture and timeline UI.
- Consumes: `displayWorkouts` and `raceEntries`.

- [ ] **Step 1: Add type**

In `frontend/src/types.ts`:

```ts
export interface PlanPhase {
  id: string
  label: string
  status: 'done' | 'current' | 'next'
  summary: string
}
```

- [ ] **Step 2: Add fixture**

In `frontend/src/fixtures.ts`:

```ts
export const planPhases: PlanPhase[] = [
  { id: 'base', label: 'Base', status: 'done', summary: '穩定跑量' },
  { id: 'build', label: 'Build', status: 'current', summary: '累積馬拉松節奏' },
  { id: 'peak', label: 'Peak', status: 'next', summary: '最高訓練週' },
  { id: 'taper', label: 'Taper', status: 'next', summary: '降低疲勞' },
  { id: 'race', label: 'Race', status: 'next', summary: '比賽執行' },
]
```

Add `PlanPhase` to the type import.

- [ ] **Step 3: Add failing test**

```ts
it('shows Plan as a race-track journey with schedule underneath', async () => {
  const wrapper = mount(App)

  await wrapper.get('button[data-view="plan"]').trigger('click')

  expect(wrapper.get('[data-testid="plan-journey"]').text()).toContain('Build')
  expect(wrapper.get('[data-testid="plan-journey"]').text()).toContain('Race')
  expect(wrapper.text()).toContain('接下來課表')
})
```

- [ ] **Step 4: Run the test to verify it fails**

Run: `cd frontend && npm run test -- App.test.ts -t "race-track journey"`

Expected: FAIL because `plan` route and timeline are missing.

- [ ] **Step 5: Import and render phases**

In `frontend/src/App.vue`, import `planPhases as fixturePlanPhases`.

Add:

```ts
const planPhases = computed(() => fixturePlanPhases)
```

Replace the old calendar top section with:

```vue
<section v-else-if="activeView === 'plan'" class="page-stack plan-page" aria-labelledby="plan-title">
  <div class="page-heading page-heading--with-action">
    <div>
      <span>Race journey</span>
      <h2 id="plan-title">計畫</h2>
    </div>
    <AppButton tone="primary" @click="isRaceGoalModalOpen = true">新增目標</AppButton>
  </div>
  <section class="surface-card plan-journey" data-testid="plan-journey" aria-label="訓練階段">
    <article v-for="phase in planPhases" :key="phase.id" class="plan-phase" :class="`plan-phase--${phase.status}`">
      <span>{{ phase.label }}</span>
      <strong>{{ phase.summary }}</strong>
    </article>
  </section>
  <section class="schedule-section" aria-labelledby="schedule-title">
    <h3 id="schedule-title">接下來課表</h3>
    <!-- Move the existing workout list markup here unchanged. -->
  </section>
</section>
```

Move the existing workout list from the old calendar view into `schedule-section` without changing its workout-detail actions.

- [ ] **Step 6: Run the test**

Run: `cd frontend && npm run test -- App.test.ts -t "race-track journey"`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/types.ts frontend/src/fixtures.ts frontend/src/App.vue frontend/src/App.test.ts
git commit -m "feat: add plan journey timeline"
```

---

### Task 5: Johnny Reasoning Center

**Files:**
- Modify: `frontend/src/App.vue`
- Test: `frontend/src/App.test.ts`

**Interfaces:**
- Consumes: `displayInboxItems`, `pendingInboxItems`, `historicalInboxItems`, existing recommendation actions.
- Produces: public Johnny page with pending recommendations first and conversation hidden.

- [ ] **Step 1: Add failing test**

```ts
it('shows Johnny as recommendations first and hides public conversation', async () => {
  const wrapper = mount(App)

  await wrapper.get('button[data-view="johnny"]').trigger('click')

  expect(wrapper.get('[data-testid="johnny-page"]').text()).toContain('待決定')
  expect(wrapper.get('[data-testid="johnny-page"]').text()).toContain('賽前 9 天降低長跑壓力')
  expect(wrapper.text()).not.toContain('送出')
  expect(wrapper.text()).not.toContain('今天原本有 8 km')
})
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npm run test -- App.test.ts -t "recommendations first"`

Expected: FAIL because the public view is still `inbox` or conversation content is exposed.

- [ ] **Step 3: Replace the public inbox branch**

Change:

```vue
<section v-else-if="activeView === 'inbox'" ...>
```

to:

```vue
<section v-else-if="activeView === 'johnny'" class="page-stack johnny-page" data-testid="johnny-page" aria-labelledby="johnny-title">
```

Set heading:

```vue
<h2 id="johnny-title">Johnny</h2>
```

- [ ] **Step 4: Add weekly review block under pending recommendations**

After the pending recommendations section, add:

```vue
<section class="surface-card johnny-review" aria-labelledby="johnny-review-title">
  <span class="card-kicker">Weekly review</span>
  <h3 id="johnny-review-title">這週先守住連續性</h3>
  <p>Johnny 會把待決定建議、恢復訊號和計畫變動放在這裡。Conversation 功能目前尚未公開。</p>
</section>
```

- [ ] **Step 5: Ensure conversation branch cannot be reached from nav**

Keep the `activeView === 'conversation'` branch in code only for future tests and direct internal use. Do not include it in `navItems`.

- [ ] **Step 6: Run the test**

Run: `cd frontend && npm run test -- App.test.ts -t "recommendations first"`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/App.vue frontend/src/App.test.ts
git commit -m "feat: reshape Johnny reasoning center"
```

---

### Task 6: Athlete Baseline And Data Signal Coverage

**Files:**
- Modify: `frontend/src/types.ts`
- Modify: `frontend/src/fixtures.ts`
- Modify: `frontend/src/App.vue`
- Test: `frontend/src/App.test.ts`

**Interfaces:**
- Produces: `AthleteBaselineSnapshot`, `SignalCoverageItem`.
- Consumes: `athleteSettings`, `recoveryEvidence`, `garminConnection`.

- [ ] **Step 1: Add types**

In `frontend/src/types.ts`:

```ts
export interface AthleteBaselineSnapshot {
  weeklyMileage: string
  experience: string
  injuryStatus: string
  rhythm: string
  recentMetrics: string[]
}

export interface SignalCoverageItem {
  id: 'activity' | 'sleep' | 'hrv' | 'resting_hr' | 'training_load' | 'athlete_baseline'
  label: string
  covered: boolean
  source: string
}
```

- [ ] **Step 2: Add failing tests**

```ts
it('shows Athlete baseline before the settings form', async () => {
  const wrapper = mount(App)

  await wrapper.get('button[data-view="athlete"]').trigger('click')

  expect(wrapper.get('[data-testid="athlete-baseline"]').text()).toContain('Athlete Baseline')
  expect(wrapper.get('[data-testid="athlete-baseline"]').text()).toContain('週跑量')
  expect(wrapper.find('[data-testid="athlete-baseline"]').element.compareDocumentPosition(wrapper.get('[data-testid="athlete-settings-form"]').element)).toBe(Node.DOCUMENT_POSITION_FOLLOWING)
})

it('shows Data signal coverage before provider details', async () => {
  const wrapper = mount(App)

  await wrapper.get('button[data-view="data"]').trigger('click')

  expect(wrapper.get('[data-testid="signal-coverage"]').text()).toContain('Johnny 已有')
  expect(wrapper.get('[data-testid="signal-coverage"]').text()).toContain('Activity')
  expect(wrapper.get('[data-testid="signal-coverage"]').text()).toContain('Athlete Baseline')
})
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd frontend && npm run test -- App.test.ts -t "Athlete baseline|Data signal coverage"`

Expected: FAIL because the new sections do not exist.

- [ ] **Step 4: Add baseline helper**

In `frontend/src/App.vue`:

```ts
const athleteBaselineSnapshot = computed<AthleteBaselineSnapshot>(() => ({
  weeklyMileage: `${athleteSettings.value.currentWeeklyMileage || '0'} ${athleteMileageDisplayUnit.value === 'imperial' ? 'mi' : 'km'}`,
  experience: athleteSettings.value.experienceLevel || '未設定',
  injuryStatus: formatInjuryStatusLabel(athleteSettings.value.injuryStatus),
  rhythm: `${athleteSettings.value.preferredTrainingDays.length} 天訓練 · 長跑 ${formatWeekdayLabel(athleteSettings.value.preferredLongRunDay)}`,
  recentMetrics: recoveryEvidence.value.slice(0, 3).map((item) => `${item.metric} ${item.value}`),
}))
```

If `formatInjuryStatusLabel` or `formatWeekdayLabel` does not exist, add:

```ts
function formatInjuryStatusLabel(status: string): string {
  const labels: Record<string, string> = {
    none: '無目前傷痛',
    current: '目前有傷痛',
    recent: '近期傷痛觀察',
    recurring: '反覆傷痛觀察',
  }
  return labels[status] ?? '未設定'
}

function formatWeekdayLabel(day: string): string {
  const labels: Record<string, string> = {
    monday: '週一',
    tuesday: '週二',
    wednesday: '週三',
    thursday: '週四',
    friday: '週五',
    saturday: '週六',
    sunday: '週日',
  }
  return labels[day] ?? day
}
```

- [ ] **Step 5: Add signal coverage helper**

```ts
const signalCoverage = computed<SignalCoverageItem[]>(() => {
  const metrics = new Set(recoveryEvidence.value.map((item) => item.metric.toLowerCase()))
  return [
    { id: 'activity', label: 'Activity', covered: hasActiveDataProvider.value, source: 'Garmin' },
    { id: 'sleep', label: 'Sleep', covered: metrics.has('睡眠') || metrics.has('sleep'), source: 'Garmin' },
    { id: 'hrv', label: 'HRV', covered: metrics.has('hrv'), source: 'Garmin' },
    { id: 'resting_hr', label: 'Resting HR', covered: !unavailableSignals.value.some((item) => item.includes('靜息心率')), source: 'Garmin' },
    { id: 'training_load', label: 'Training Load', covered: recoveryEvidence.value.some((item) => item.metric.includes('負荷')), source: 'Johnny Analytics' },
    { id: 'athlete_baseline', label: 'Athlete Baseline', covered: Boolean(athleteSettings.value.timezone), source: '運動員' },
  ]
})

const coveredSignalCount = computed(() => signalCoverage.value.filter((item) => item.covered).length)
```

- [ ] **Step 6: Render Athlete baseline before form**

In the `activeView === 'athlete'` section, place before the form:

```vue
<section class="surface-card athlete-baseline" data-testid="athlete-baseline" aria-labelledby="athlete-baseline-title">
  <span class="card-kicker">Athlete Baseline</span>
  <h3 id="athlete-baseline-title">Johnny 用來個人化你的基準</h3>
  <dl>
    <div><dt>週跑量</dt><dd>{{ athleteBaselineSnapshot.weeklyMileage }}</dd></div>
    <div><dt>經驗</dt><dd>{{ athleteBaselineSnapshot.experience }}</dd></div>
    <div><dt>傷痛狀態</dt><dd>{{ athleteBaselineSnapshot.injuryStatus }}</dd></div>
    <div><dt>訓練節奏</dt><dd>{{ athleteBaselineSnapshot.rhythm }}</dd></div>
  </dl>
  <p>{{ athleteBaselineSnapshot.recentMetrics.join(' · ') }}</p>
</section>
```

- [ ] **Step 7: Render Signal Coverage before provider cards**

In the `activeView === 'data'` section, place before provider cards:

```vue
<section class="surface-card signal-coverage" data-testid="signal-coverage" aria-labelledby="signal-coverage-title">
  <span class="card-kicker">Signal Coverage</span>
  <h3 id="signal-coverage-title">Johnny 已有 {{ coveredSignalCount }}/{{ signalCoverage.length }} 個訓練訊號</h3>
  <div class="signal-coverage__grid">
    <span v-for="item in signalCoverage" :key="item.id" class="signal-pill" :class="{ 'signal-pill--covered': item.covered }">
      <strong>{{ item.label }}</strong>
      <small>{{ item.source }}</small>
    </span>
  </div>
</section>
```

- [ ] **Step 8: Run tests**

Run: `cd frontend && npm run test -- App.test.ts -t "Athlete baseline|Data signal coverage"`

Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add frontend/src/types.ts frontend/src/App.vue frontend/src/App.test.ts
git commit -m "feat: add athlete baseline and signal coverage"
```

---

### Task 7: Light Mint Runtime Styling

**Files:**
- Modify: `frontend/src/styles.css`
- Test: `frontend/src/App.test.ts`

**Interfaces:**
- Consumes: class names introduced in Tasks 1-6.
- Produces: runtime CSS variables matching `DESIGN.md`, mobile bottom nav, desktop context rail.

- [ ] **Step 1: Add token drift expectation**

Run existing token verifier before edits:

```bash
cd frontend && npm run verify:tokens
```

Expected: FAIL or PASS based on current drift. Record output before changing tokens.

- [ ] **Step 2: Update root CSS variables**

In `frontend/src/styles.css`, update `:root` variables to match `DESIGN.md`:

```css
--color-mint-track: #eef9f1;
--color-mint-surface: #f8fcf8;
--color-card-white: #ffffff;
--color-deep-green: #0f4a32;
--color-lane-green: #2d7a58;
--color-soft-mint: #bfe8d2;
--color-split-amber: #d89422;
--color-rest-blue: #6c9ecf;
--color-effort-red: #b85a50;
--color-ink-green: #14382a;
--color-muted-green: #5f7b6b;
--color-line-mint: #d9ecdd;
```

Map existing semantic variables for compatibility:

```css
--color-primary: var(--color-deep-green);
--color-track-night: var(--color-mint-track);
--color-pit-black: var(--color-deep-green);
--color-rubber-gray: var(--color-card-white);
--color-lane-chalk: var(--color-ink-green);
--color-muted-chalk: var(--color-muted-green);
--color-recovery-blue: var(--color-rest-blue);
--color-easy-green: var(--color-soft-mint);
--color-line-white: var(--color-card-white);
```

- [ ] **Step 3: Implement light shell and nav**

Add or update:

```css
body {
  background:
    linear-gradient(90deg, rgba(15, 74, 50, 0.035) 1px, transparent 1px) 0 0 / 4.5rem 100%,
    var(--color-mint-track);
}

.app-shell {
  color: var(--color-ink-green);
}

.top-bar {
  border-bottom: 1px solid var(--color-line-mint);
  background: color-mix(in srgb, var(--color-mint-track) 88%, white);
  backdrop-filter: blur(14px);
}

.top-nav {
  background: var(--color-card-white);
  border-color: var(--color-line-mint);
  box-shadow: 0 1rem 2.4rem rgba(15, 74, 50, 0.08);
}

.top-nav__item {
  color: var(--color-muted-green);
}

.top-nav__item--active {
  border-color: color-mix(in srgb, var(--color-deep-green) 65%, var(--color-line-mint));
  color: var(--color-deep-green);
  background: var(--color-soft-mint);
}
```

- [ ] **Step 4: Add Today Decision styling**

```css
.today-decision-card {
  display: grid;
  gap: 1rem;
  padding: clamp(1rem, 3vw, 1.4rem);
  border-radius: var(--radius-xl);
  box-shadow: 0 1.2rem 2.8rem rgba(15, 74, 50, 0.18);
}

.today-decision-card--run {
  color: var(--color-card-white);
  background: var(--color-deep-green);
}

.today-decision-card--adjust {
  color: var(--color-ink-green);
  background: var(--color-split-amber);
}

.today-decision-card--rest {
  color: var(--color-card-white);
  background: var(--color-rest-blue);
}

.today-evidence-chip-list {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 0.5rem;
}

.today-evidence-chip {
  display: grid;
  gap: 0.1rem;
  padding: 0.65rem;
  border: 1px solid rgba(255, 255, 255, 0.35);
  border-radius: var(--radius-md);
  background: rgba(255, 255, 255, 0.16);
}

@media (max-width: 640px) {
  .today-evidence-chip-list {
    grid-template-columns: 1fr;
  }
}
```

- [ ] **Step 5: Add weekly activity, plan, baseline, and signal styles**

Implement classes introduced in earlier tasks:

```css
.weekly-activity__bars,
.signal-coverage__grid,
.plan-journey,
.athlete-baseline dl {
  display: grid;
  gap: 0.75rem;
}

.weekly-activity__bars {
  grid-template-columns: repeat(7, minmax(0, 1fr));
  align-items: end;
  min-height: 10rem;
}

.weekly-activity__bar {
  display: block;
  height: max(0.5rem, var(--bar-size));
  border-radius: var(--radius-full);
  background: var(--color-lane-green);
}

.plan-journey {
  grid-template-columns: repeat(5, minmax(0, 1fr));
}

.plan-phase {
  border: 1px solid var(--color-line-mint);
  border-radius: var(--radius-lg);
  padding: 0.8rem;
  background: var(--color-mint-surface);
}

.plan-phase--current {
  border-color: var(--color-deep-green);
  background: var(--color-soft-mint);
}

.signal-pill {
  border: 1px solid var(--color-line-mint);
  border-radius: var(--radius-full);
  padding: 0.55rem 0.75rem;
  background: var(--color-mint-surface);
}

.signal-pill--covered {
  border-color: var(--color-lane-green);
  background: var(--color-soft-mint);
}
```

- [ ] **Step 6: Add responsive desktop Today layout**

```css
.today-layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(16rem, 22rem);
  gap: var(--space-shell-gap);
  align-items: start;
}

.today-main-column,
.today-context-rail {
  display: grid;
  gap: var(--space-shell-gap);
}

@media (max-width: 860px) {
  .today-layout {
    grid-template-columns: 1fr;
  }
}
```

- [ ] **Step 7: Run token verifier**

Run: `cd frontend && npm run verify:tokens`

Expected: PASS after `DESIGN.md` and CSS variables agree, or a specific failure that identifies remaining token mapping work.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/styles.css
git commit -m "style: apply light mint Johnny runtime theme"
```

---

### Task 8: Full Verification And Cleanup

**Files:**
- Modify as needed: `frontend/src/App.vue`, `frontend/src/styles.css`, `frontend/src/App.test.ts`
- Evidence: `premium-audit.json`

**Interfaces:**
- Consumes: all prior tasks.
- Produces: passing frontend checks and premium audit evidence.

- [ ] **Step 1: Run all frontend tests**

Run:

```bash
cd frontend && npm run test
```

Expected: PASS.

- [ ] **Step 2: Run production build**

Run:

```bash
cd frontend && npm run build
```

Expected: PASS.

- [ ] **Step 3: Run token verification**

Run:

```bash
cd frontend && npm run verify:tokens
```

Expected: PASS.

- [ ] **Step 4: Run premium audit**

Run:

```bash
python /Users/fangchangseng/.codex/plugins/cache/openai-curated-remote/frontend-design-premium/1.4.0/skills/frontend-design-premium/scripts/audit_project.py /Users/fangchangseng/Desktop/Projects/Johnny --mode strict
```

Expected: PASS or structured findings in `premium-audit.json`. Fix blocking findings before continuing.

- [ ] **Step 5: Search for native dialogs**

Run:

```bash
rg -n "alert\\(|confirm\\(|prompt\\(" frontend/src
```

Expected: no matches.

- [ ] **Step 6: Search for old production nav labels**

Run:

```bash
rg -n "訓練安排|Agent 收件匣|運動員設定|資料來源" frontend/src
```

Expected: no matches in public UI code. Test names may mention old labels only when explicitly asserting their absence.

- [ ] **Step 7: Run local visual inspection**

Run:

```bash
cd frontend && npm run dev
```

Open the served URL and inspect:

- narrow mobile width around 390px;
- desktop width around 1280px;
- `今日`, `計畫`, `Johnny`, `運動員`, `資料`;
- keyboard focus through bottom/top navigation, Today action, recommendation actions, athlete form, provider form;
- no clipped text in Chinese labels.

- [ ] **Step 8: Commit verification fixes**

If any verification fixes are needed:

```bash
git add frontend/src frontend/package.json premium-audit.json
git commit -m "chore: verify Johnny start-line UI"
```

If no fixes are needed after Task 7, skip the commit.

---

## Self-Review

- Spec coverage: Tasks cover navigation, Today Decision, weekly activity chart, Plan journey, Johnny recommendations, Athlete Baseline, Data Signal Coverage, runtime theme, and verification.
- Placeholder scan: The plan contains concrete file paths, code snippets, commands, and expected outcomes.
- Type consistency: New types are defined before consumers use them; task names use the final view keys `plan`, `johnny`, `athlete`, and `data`.
- Risk: The plan intentionally keeps backend APIs unchanged and hides conversation from the public route model.
