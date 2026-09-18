# Johnny Training Plan Generation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build manual and background training plan generation that creates complete, safe Active Projections from deterministic Plan Skeletons with LLM enrichment.

**Architecture:** Implement this in stages from lowest-risk domain contracts upward. Backend domain validation owns completeness, phase coverage, hard-session limits, and atomic activation; product APIs wrap agent runs with quota and in-flight behavior; the frontend consumes product APIs through a thin regeneration sheet without introducing a draft-preview workflow.

**Tech Stack:** FastAPI, Pydantic, SQLAlchemy, Alembic, pytest, Vue 3, TypeScript, Vitest.

**Spec:** `docs/superpowers/specs/2026-09-17-johnny-training-plan-generation.md`

## Global Constraints

- Manual regeneration starts tomorrow in the athlete's timezone and never rewrites today's workout.
- Each Plan Version covers at most 16 weeks.
- Race-based projections end on race day; post-race rest is represented by Recovery Window.
- Johnny deterministic planning owns Plan Skeleton dates, weekly structure, phase coverage, and completeness.
- The LLM may enrich workout intent and structured details but must not move dates or change weekly structure.
- Incomplete generated output must never be saved as an Active Projection.
- `metadata.phase_segments` is the canonical timeline.
- Every workout must have a `phase` that matches exactly one Phase Segment.
- V1 Plan Phase enum is `base | build | peak | taper | race | maintenance`.
- V1 Hard Session workout types are `interval | tempo | hill | long_run`.
- V1 `max_hard_sessions_per_week` accepts `0..2`, defaults to `2`, and is safety-capped.
- Manual Regeneration Quota is one successful Active Projection regeneration per athlete-local calendar day.
- Background generation does not consume Regeneration Quota.

---

## Stage 1: Domain Contracts And Persistence

Stage goal: make the domain able to represent the new plan rules without introducing generation behavior yet.

### Task 1: Athlete Baseline Hard Session Capacity

**Files:**
- Modify: `backend/src/domain/athlete_race.py`
- Modify: `backend/src/api/schemas/athlete_profile.py`
- Modify: `backend/src/api/routes/athlete_profile.py`
- Modify: `backend/src/api/routes/auth.py`
- Modify: `backend/src/infrastructure/database/athlete_race_repository.py`
- Modify: `backend/src/application/agent_tools.py`
- Modify: `frontend/src/types.ts`
- Modify: `frontend/src/App.vue`
- Test: `backend/tests/unit/test_athlete_race_domain.py`
- Test: `backend/tests/unit/test_athlete_race_api.py`
- Test: `backend/tests/integration/database/test_repositories.py`
- Test: `frontend/src/App.test.ts`

**Interfaces:**
- Produces: `AthletePreferences.max_hard_sessions_per_week: int`
- Produces API field: `max_hard_sessions_per_week`
- Produces frontend form field: `maxHardSessionsPerWeek: string`
- Consumes existing `max_runs_per_week` and injury fields for later safety caps.

- [ ] **Step 1: Write backend domain tests**

Add tests that prove default `2`, accepted values `0`, `1`, `2`, and rejection of `3` and `-1`.

Run: `./.venv/bin/pytest backend/tests/unit/test_athlete_race_domain.py -q`

Expected: FAIL because `max_hard_sessions_per_week` does not exist yet.

- [ ] **Step 2: Add domain field and validation**

Update `AthletePreferences` and `AthleteProfile.create(...)` with:

```python
max_hard_sessions_per_week: int = 2
```

Validate:

```python
if self.max_hard_sessions_per_week < 0 or self.max_hard_sessions_per_week > 2:
    raise DomainValidationError("maximum hard sessions per week must be between 0 and 2")
```

- [ ] **Step 3: Round-trip through API and repository**

Expose `max_hard_sessions_per_week` in `AthleteProfileRequest`, `AthleteProfileResponse`, route mapping, repository metadata, and `AthleteContextTool._profile_payload`.

Run: `./.venv/bin/pytest backend/tests/unit/test_athlete_race_api.py backend/tests/integration/database/test_repositories.py -q`

Expected: PASS.

- [ ] **Step 4: Add frontend field**

Add `maxHardSessionsPerWeek` to `AthleteSettingsForm`, `defaultAthleteSettingsForm`, profile hydration, payload validation, and the athlete settings form near `maxRunsPerWeek`.

Use label `質量課表` and supporting copy `包含間歇、節奏、坡跑與長跑。Johnny 會依恢復與傷痛狀態下修。`

- [ ] **Step 5: Verify**

Run: `cd frontend && npm run test -- App.test.ts -t "athlete"`

Expected: PASS after updating tests to assert the new field saves and hydrates.

### Task 2: Training Plan Domain Phase And Workout Type Validation

**Files:**
- Modify: `backend/src/domain/training_plan.py`
- Modify: `backend/src/api/schemas/training_plans.py`
- Modify: `backend/src/infrastructure/llm/openai_gateway.py`
- Modify: `frontend/src/types.ts`
- Modify: `frontend/src/App.vue`
- Test: `backend/tests/unit/test_training_plan_domain.py` if present, otherwise create `backend/tests/unit/test_training_plan_generation_domain.py`
- Test: `backend/tests/unit/test_openai_gateway.py`
- Test: `frontend/src/App.test.ts`

**Interfaces:**
- Produces: `SUPPORTED_PLAN_PHASES = {"base", "build", "peak", "taper", "race", "maintenance"}`
- Produces: `SUPPORTED_WORKOUT_TYPES` includes `hill`
- Produces: `validate_phase_segments(plan: TrainingPlan) -> None`
- Produces: `is_hard_session(workout: Workout) -> bool`

- [ ] **Step 1: Write failing phase validation tests**

Cover valid continuous segments, gap rejection, overlap rejection, workout phase mismatch rejection, and missing workout phase rejection.

Run: `./.venv/bin/pytest backend/tests/unit/test_training_plan_generation_domain.py -q`

Expected: FAIL because helpers do not exist yet.

- [ ] **Step 2: Add enum constants and `hill`**

Add `hill` to `SUPPORTED_WORKOUT_TYPES`.

Add `SUPPORTED_PLAN_PHASES`.

Validate `Workout.phase` when present:

```python
if self.phase is not None and self.phase not in SUPPORTED_PLAN_PHASES:
    raise DomainValidationError("workout phase is not supported")
```

- [ ] **Step 3: Add plan-level phase segment validation**

Implement `validate_phase_segments(plan)` in `training_plan.py`. It reads `plan.metadata["phase_segments"]`, parses inclusive dates, verifies full coverage, non-overlap, enum membership, and every workout phase/date match.

- [ ] **Step 4: Wire validation into active-plan creation path**

Call `validate_phase_segments(plan)` before `CreateTrainingPlanTool` persists active plans and before product regeneration service activation in later tasks. Keep existing generic `TrainingPlan.create(...)` permissive enough for legacy fixtures until repository write paths enforce new generated-plan rules.

- [ ] **Step 5: Update API and LLM schemas**

Add `hill` to Pydantic and OpenAI gateway workout type enum. Keep workout step `hill` unchanged.

Run: `./.venv/bin/pytest backend/tests/unit/test_openai_gateway.py -q`

Expected: PASS.

### Task 3: Atomic Active Projection Replacement

**Files:**
- Modify: `backend/src/infrastructure/database/training_plan_repository.py`
- Test: `backend/tests/integration/database/test_repositories.py`

**Interfaces:**
- Produces: `create_active_plan(user_id: str, plan: TrainingPlan, replace_all_active: bool = False) -> TrainingPlan`
- Consumes domain validation from Task 2.

- [ ] **Step 1: Write repository tests**

Add tests for:

- Race-based active plan supersedes previous active plan for same race.
- Maintenance plan with `replace_all_active=True` supersedes previous race-based active plan.
- Failed save leaves existing active plan unchanged.
- Superseded workout completion statuses remain on historical plan.

Run: `./.venv/bin/pytest backend/tests/integration/database/test_repositories.py -q`

Expected: FAIL for maintenance replacement behavior.

- [ ] **Step 2: Add explicit replacement option**

Change `create_active_plan` signature to accept `replace_all_active=False`. When true, collect all active plans for the user as conflicts. When false, preserve existing conflict behavior.

- [ ] **Step 3: Save then supersede in one session transaction**

Keep persistence and superseding in the same SQLAlchemy session flush. Do not commit inside repository methods.

- [ ] **Step 4: Verify**

Run: `./.venv/bin/pytest backend/tests/integration/database/test_repositories.py -q`

Expected: PASS.

---

## Stage 2: Deterministic Planning Core

Stage goal: create pure application services that can be tested without FastAPI, workers, or frontend state.

### Task 4: Race Strategy And Horizon Selection

**Files:**
- Create: `backend/src/application/training_plan_generation.py`
- Test: `backend/tests/unit/test_training_plan_generation.py`

**Interfaces:**
- Produces dataclass `RaceStrategySelection(race_id: str | None, plan_type: str, reason: str)`
- Produces `select_race_strategy(race_goals: Sequence[dict], anchor: date, explicit_race_id: str | None, force_maintenance: bool) -> RaceStrategySelection`
- Produces `projection_window(anchor: date, race_date: date | None, plan_type: str) -> tuple[date, date]`

- [ ] **Step 1: Write selection tests**

Cover priority order, nearest same-priority race, explicit race id, maintenance override, no-race maintenance, and race farther than 16 weeks.

Run: `./.venv/bin/pytest backend/tests/unit/test_training_plan_generation.py -q`

Expected: FAIL because module does not exist.

- [ ] **Step 2: Implement pure selection functions**

Use priority rank:

```python
RACE_PRIORITY_RANK = {"primary": 0, "secondary": 1, "tune_up": 2}
```

For manual generation, `anchor` is tomorrow. For race windows, cap at `anchor + timedelta(weeks=16) - timedelta(days=1)`.

- [ ] **Step 3: Verify**

Run: `./.venv/bin/pytest backend/tests/unit/test_training_plan_generation.py -q`

Expected: PASS.

### Task 5: Plan Skeleton Builder And Safety Rules

**Files:**
- Modify: `backend/src/application/training_plan_generation.py`
- Test: `backend/tests/unit/test_training_plan_generation.py`

**Interfaces:**
- Produces dataclass `SkeletonWorkout(scheduled_for: date, workout_type: str, phase: str, planned_duration_minutes: int | None, planned_distance_meters: int | None)`
- Produces dataclass `PlanSkeleton(starts_on: date, ends_on: date, phase_segments: list[dict], workouts: list[SkeletonWorkout])`
- Produces `effective_hard_session_limit(max_runs_per_week: int, max_hard_sessions_per_week: int, injury_status: str) -> int`
- Produces `build_plan_skeleton(...) -> PlanSkeleton`

- [ ] **Step 1: Write skeleton tests**

Cover:

- Maintenance creates 4 weeks with one `maintenance` segment.
- Race plan creates phase segments covering the whole horizon.
- Each week has workouts matching baseline capacity.
- `interval`, `tempo`, `hill`, `long_run` count as hard.
- Hard sessions are not adjacent.
- Long run is not adjacent to another hard session.
- Low-volume athletes with `max_runs_per_week=2` produce no more than one hard session.

Run: `./.venv/bin/pytest backend/tests/unit/test_training_plan_generation.py -q`

Expected: FAIL because skeleton builder does not exist.

- [ ] **Step 2: Implement effective hard-session limit**

Use:

```python
limit = min(max_hard_sessions_per_week, math.ceil(max_runs_per_week / 2), 2)
if injury_status in {"current", "recent"}:
    limit = min(limit, 1)
```

- [ ] **Step 3: Implement weekly workout placement**

Use preferred training days when present. Put long run on `preferred_long_run_day`. Fill remaining days in preferred order. If preferred days are empty, use Tuesday, Thursday, Sunday.

- [ ] **Step 4: Implement phase segments**

For maintenance, one segment. For race plan, divide available weeks into base/build/peak/taper/race with taper in the final 1-2 weeks when race is inside the horizon.

- [ ] **Step 5: Verify**

Run: `./.venv/bin/pytest backend/tests/unit/test_training_plan_generation.py -q`

Expected: PASS.

### Task 6: Completion Validation And Repair

**Files:**
- Modify: `backend/src/application/training_plan_generation.py`
- Test: `backend/tests/unit/test_training_plan_generation.py`

**Interfaces:**
- Produces dataclass `CompletionRepairResult(plan: TrainingPlan, repaired_week_indexes: list[int], repaired_workout_ids: list[str], reason: str | None)`
- Produces `validate_generated_plan(plan: TrainingPlan, skeleton: PlanSkeleton) -> list[str]`
- Produces `repair_generated_plan(plan: TrainingPlan, skeleton: PlanSkeleton, reason: str) -> CompletionRepairResult`

- [ ] **Step 1: Write validation and repair tests**

Cover partial 2-week generated plan for 8-week skeleton, invalid phase, missing workout steps for interval, and valid weeks preserved during repair.

Run: `./.venv/bin/pytest backend/tests/unit/test_training_plan_generation.py -q`

Expected: FAIL because validation and repair functions do not exist.

- [ ] **Step 2: Implement validator**

Compare generated plan against skeleton dates and workout count per week. Validate phase segments through Task 2 helper. Treat missing key-session steps as invalid for `interval`, `tempo`, and `hill`.

- [ ] **Step 3: Implement deterministic repair templates**

Use template workouts with valid steps:

- `easy_run`: one `free_run` easy target.
- `long_run`: one `free_run` easy target.
- `tempo`: warmup, threshold work, cooldown.
- `interval`: warmup, repeat block, cooldown.
- `hill`: warmup, hill repeat block, cooldown.

- [ ] **Step 4: Write repair metadata**

Ensure returned plan metadata includes:

```python
metadata["internal"]["completion_repair"] = {
    "repaired_week_indexes": repaired_week_indexes,
    "repaired_workout_ids": repaired_workout_ids,
    "reason": reason,
}
```

- [ ] **Step 5: Verify**

Run: `./.venv/bin/pytest backend/tests/unit/test_training_plan_generation.py -q`

Expected: PASS.

---

## Stage 3: Product API, Quota, And In-Flight Runs

Stage goal: add the product API that the frontend will use, while still allowing existing agent-run APIs to work.

### Task 7: Regeneration API Schemas And Routes

**Files:**
- Create: `backend/src/api/schemas/training_plan_regeneration.py`
- Create: `backend/src/api/routes/training_plan_regeneration.py`
- Modify: `backend/src/main.py`
- Test: `backend/tests/unit/test_product_workflow_api.py`

**Interfaces:**
- Produces `GET /api/v1/training-plans/regeneration-options`
- Produces `POST /api/v1/training-plans/regenerations`
- Request: `{ "client_request_id": "...", "race_id": "...", "plan_type": "race" | "maintenance" }`
- Response includes `quota`, `default_strategy`, `in_flight_run`, `run`.

- [ ] **Step 1: Write API tests**

Add tests for options payload, quota exhausted payload, maintenance selection, and in-flight reuse.

Run: `./.venv/bin/pytest backend/tests/unit/test_product_workflow_api.py -q`

Expected: FAIL because routes do not exist.

- [ ] **Step 2: Add schema classes**

Create request and response models:

```python
class TrainingPlanRegenerationRequest(BaseModel):
    client_request_id: str = Field(min_length=1, max_length=120)
    race_id: str | None = None
    plan_type: Literal["race", "maintenance"] = "race"
```

- [ ] **Step 3: Implement route shell**

The route uses `CurrentUserDependency`, `SessionDependency`, race repository, profile repository, agent run repository, and task queue.

- [ ] **Step 4: Register router**

Include router in `backend/src/main.py` after `training_plans_router` or beside it.

- [ ] **Step 5: Verify**

Run: `./.venv/bin/pytest backend/tests/unit/test_product_workflow_api.py -q`

Expected: PASS for route contracts once service from Task 8 is in place.

### Task 8: Regeneration Product Service

**Files:**
- Create: `backend/src/application/training_plan_regeneration.py`
- Modify: `backend/src/api/routes/training_plan_regeneration.py`
- Test: `backend/tests/unit/test_training_plan_regeneration.py`
- Test: `backend/tests/unit/test_product_workflow_api.py`

**Interfaces:**
- Produces `TrainingPlanRegenerationService.options(user_id: str, today: date) -> RegenerationOptions`
- Produces `TrainingPlanRegenerationService.start(user_id: str, request: TrainingPlanRegenerationRequest, today: date) -> RegenerationStartResult`

- [ ] **Step 1: Write service tests**

Cover athlete timezone day, one successful regeneration per day, failed run does not consume quota, in-flight run reused, and `client_request_id` idempotency.

Run: `./.venv/bin/pytest backend/tests/unit/test_training_plan_regeneration.py -q`

Expected: FAIL because service does not exist.

- [ ] **Step 2: Implement quota lookup**

V1 quota can be derived from completed successful `training_plan_generation` agent runs whose metadata includes:

```python
{"manual_regeneration": True, "quota_day": "2026-09-17", "created_training_plan_id": "..."}
```

If the repository cannot query metadata conveniently, add a repository method that lists today's user runs and filter in application code.

- [ ] **Step 3: Implement in-flight lookup**

Reuse queued or processing `training_plan_generation` runs for the user when run metadata has `manual_regeneration=True`.

- [ ] **Step 4: Queue run with product payload**

Use idempotency key:

```python
f"training_plan_regeneration:{user_id}:{quota_day}:{client_request_id}"
```

Payload includes `race_id`, `plan_type`, `starts_on`, `plan_horizon_weeks`, `client_request_id`, and `manual_regeneration=True`.

- [ ] **Step 5: Verify**

Run: `./.venv/bin/pytest backend/tests/unit/test_training_plan_regeneration.py backend/tests/unit/test_product_workflow_api.py -q`

Expected: PASS.

---

## Stage 4: Agent Runtime Integration And Persistence Safety

Stage goal: connect deterministic skeleton and repair to the generation workflow.

### Task 9: Agent Runtime Uses Skeleton Context

**Files:**
- Modify: `backend/src/application/agent_runtime.py`
- Modify: `backend/src/application/agent_tools.py`
- Modify: `backend/src/infrastructure/llm/local_gateway.py`
- Test: `backend/tests/unit/test_running_companion_agent.py`
- Test: `backend/tests/unit/test_local_gateway.py`

**Interfaces:**
- Consumes `build_plan_skeleton(...)`
- Produces model context key `plan_skeleton`
- Produces trusted context keys `phase_segments`, `skeleton_workouts`, `manual_regeneration`

- [ ] **Step 1: Write runtime tests**

Add tests that assert model request context contains skeleton workouts, phase segments, and that local gateway returns workouts covering the skeleton horizon.

Run: `./.venv/bin/pytest backend/tests/unit/test_running_companion_agent.py backend/tests/unit/test_local_gateway.py -q`

Expected: FAIL because skeleton context is absent.

- [ ] **Step 2: Build skeleton during preload**

In `_training_plan_generation_preload_context`, build skeleton from selected race, athlete profile, starts_on, and plan_type.

- [ ] **Step 3: Update model prompt boundary**

Adjust training-plan-generation system message to state that dates and weekly structure come from `plan_skeleton`, and the model must call `createTrainingPlan` using those dates.

- [ ] **Step 4: Update local gateway**

Make local gateway create workouts from `context["plan_skeleton"]["workouts"]` instead of a hard-coded four-week plan.

- [ ] **Step 5: Verify**

Run: `./.venv/bin/pytest backend/tests/unit/test_running_companion_agent.py backend/tests/unit/test_local_gateway.py -q`

Expected: PASS.

### Task 10: CreateTrainingPlanTool Validates And Repairs Before Save

**Files:**
- Modify: `backend/src/application/agent_tools.py`
- Modify: `backend/src/application/agent_runtime.py`
- Test: `backend/tests/unit/test_agent_tools.py`
- Test: `backend/tests/unit/test_running_companion_agent.py`

**Interfaces:**
- Consumes `validate_generated_plan(...)`
- Consumes `repair_generated_plan(...)`
- Produces active plans only after validation and repair.

- [ ] **Step 1: Write failing tool tests**

Add tests where createTrainingPlan receives only 2 generated weeks for an 8-week skeleton and persists a repaired full plan with `metadata.internal.completion_repair`.

Run: `./.venv/bin/pytest backend/tests/unit/test_agent_tools.py -q`

Expected: FAIL because repair is not wired into the tool.

- [ ] **Step 2: Inject skeleton trusted context**

Extend `_inject_training_plan_trusted_context` to include `plan_skeleton`, `phase_segments`, and manual regeneration flags.

- [ ] **Step 3: Repair before persistence**

In `CreateTrainingPlanTool.run`, build the `TrainingPlan`, validate against skeleton, repair when needed, then call `create_active_plan(..., replace_all_active=True)` when manual regeneration or maintenance replacement requires it.

- [ ] **Step 4: Record repair in agent run steps**

Ensure repair metadata appears in the tool call output payload so agent run step logs show that Completion Repair occurred.

- [ ] **Step 5: Verify**

Run: `./.venv/bin/pytest backend/tests/unit/test_agent_tools.py backend/tests/unit/test_running_companion_agent.py -q`

Expected: PASS.

### Task 11: Successful Run Marks Quota Consumption Metadata

**Files:**
- Modify: `backend/src/application/agent_runtime.py`
- Modify: `backend/src/infrastructure/database/agent_run_repository.py`
- Test: `backend/tests/integration/database/test_agent_run_repository.py`
- Test: `backend/tests/unit/test_running_companion_agent.py`

**Interfaces:**
- Produces completed run metadata key `created_training_plan_id`
- Produces completed run metadata key `quota_day`
- Consumes product payload `manual_regeneration=True`

- [ ] **Step 1: Write metadata tests**

Assert completed manual regeneration runs include `created_training_plan_id`, `manual_regeneration`, and `quota_day`.

Run: `./.venv/bin/pytest backend/tests/integration/database/test_agent_run_repository.py backend/tests/unit/test_running_companion_agent.py -q`

Expected: FAIL because metadata is not updated on completion.

- [ ] **Step 2: Preserve queued task input metadata**

When worker/runtime resumes an existing queued run, carry request input flags into run metadata.

- [ ] **Step 3: Complete run with training plan id metadata**

When `_training_plan_id_from_payload(...)` returns an id, merge it into run metadata before `complete_run`.

- [ ] **Step 4: Verify**

Run: `./.venv/bin/pytest backend/tests/integration/database/test_agent_run_repository.py backend/tests/unit/test_running_companion_agent.py -q`

Expected: PASS.

---

## Stage 5: Background Generation

Stage goal: make plan continuity automatic without consuming manual quota.

### Task 12: Daily Background Selection Service

**Files:**
- Modify: `backend/src/application/training_plan_regeneration.py`
- Test: `backend/tests/unit/test_training_plan_regeneration.py`

**Interfaces:**
- Produces `find_users_needing_projection(today: date) -> list[BackgroundProjectionCandidate]`
- Produces `queue_background_generation(candidate) -> QueuedAgentRun`

- [ ] **Step 1: Write background service tests**

Cover active plan still running, recovery day 1-6 no-op, recovery day 7 queues run for day 8, race-based background generation, and maintenance fallback.

Run: `./.venv/bin/pytest backend/tests/unit/test_training_plan_regeneration.py -q`

Expected: FAIL because background methods do not exist.

- [ ] **Step 2: Implement Recovery Window logic**

Use previous projection `ends_on`; queue on `ends_on + 7` with `starts_on = ends_on + 8`.

- [ ] **Step 3: Use non-quota trigger metadata**

Queue run payload includes `manual_regeneration=False` and `trigger_type="scheduled"`.

- [ ] **Step 4: Verify**

Run: `./.venv/bin/pytest backend/tests/unit/test_training_plan_regeneration.py -q`

Expected: PASS.

### Task 13: Worker Entry Point For Daily Checks

**Files:**
- Modify: `backend/src/worker/handler.py`
- Modify: `backend/src/worker/main.py`
- Test: `backend/tests/integration/application/test_agent_runtime_worker_scheduler.py`

**Interfaces:**
- Consumes task type `training-plan.daily-check`
- Produces idempotent queueing for `training_plan_generation`

- [ ] **Step 1: Write worker scheduler tests**

Add tests that processing a daily-check task queues one generation task and that repeating the same daily-check does not duplicate it.

Run: `./.venv/bin/pytest backend/tests/integration/application/test_agent_runtime_worker_scheduler.py -q`

Expected: FAIL because handler only logs.

- [ ] **Step 2: Dispatch by task type**

In `process_task`, branch on `message.task_type == "training-plan.daily-check"` and call the background service.

- [ ] **Step 3: Keep sample worker support**

Keep `WORKER_SAMPLE_MESSAGE` behavior so local task simulation still works.

- [ ] **Step 4: Verify**

Run: `./.venv/bin/pytest backend/tests/integration/application/test_agent_runtime_worker_scheduler.py -q`

Expected: PASS.

---

## Stage 6: Frontend Regeneration Experience

Stage goal: expose the product flow in `計畫` without changing the current plan until generation succeeds.

### Task 14: Frontend API Client And Types

**Files:**
- Modify: `frontend/src/types.ts`
- Modify: `frontend/src/api/client.ts`
- Test: `frontend/src/App.test.ts`

**Interfaces:**
- Produces `TrainingPlanRegenerationOptions`
- Produces `TrainingPlanRegenerationRequest`
- Produces `getTrainingPlanRegenerationOptions()`
- Produces `startTrainingPlanRegeneration(payload)`

- [ ] **Step 1: Add frontend type tests through App test setup**

Update mocks in `App.test.ts` to include regeneration option payloads.

Run: `cd frontend && npm run test -- App.test.ts -t "plan"`

Expected: FAIL until client functions and App wiring exist.

- [ ] **Step 2: Add type definitions**

Add race strategy, quota, and in-flight run response types to `frontend/src/types.ts`.

- [ ] **Step 3: Add API functions**

Add:

```ts
export function getTrainingPlanRegenerationOptions(): Promise<{ data: TrainingPlanRegenerationOptions }> {
  return getJson('/training-plans/regeneration-options')
}

export function startTrainingPlanRegeneration(payload: TrainingPlanRegenerationRequest): Promise<{ data: TrainingPlanRegenerationStartResponse }> {
  return postJson('/training-plans/regenerations', payload)
}
```

- [ ] **Step 4: Verify**

Run: `cd frontend && npm run test -- App.test.ts -t "plan"`

Expected: PASS after Task 15.

### Task 15: Thin Regeneration Sheet

**Files:**
- Create: `frontend/src/components/TrainingPlanRegenerationSheet.vue`
- Modify: `frontend/src/App.vue`
- Test: `frontend/src/App.test.ts`

**Interfaces:**
- Consumes `TrainingPlanRegenerationOptions`
- Emits `confirm` with `TrainingPlanRegenerationRequest`
- Emits `close`

- [ ] **Step 1: Write frontend tests**

Add tests that:

- Plan page opens the sheet.
- Sheet shows default Race Strategy.
- Maintenance can be selected even with races present.
- Quota-exhausted state disables confirmation and shows next availability.

Run: `cd frontend && npm run test -- App.test.ts -t "regeneration"`

Expected: FAIL because component does not exist.

- [ ] **Step 2: Build component**

Use existing app modal/sheet styling patterns. Include race radio options, maintenance option, quota status, and confirm/cancel buttons.

- [ ] **Step 3: Wire App state**

Add state for options loading, sheet open, selected race/maintenance, generation busy, and in-flight run.

- [ ] **Step 4: Keep old plan visible**

After successful `startTrainingPlanRegeneration`, show generation-in-progress state but do not replace `apiWorkouts` until existing hydration fetch returns a new active plan.

- [ ] **Step 5: Verify**

Run: `cd frontend && npm run test -- App.test.ts -t "regeneration"`

Expected: PASS.

### Task 16: Plan Timeline From Phase Segments

**Files:**
- Modify: `frontend/src/types.ts`
- Modify: `frontend/src/App.vue`
- Test: `frontend/src/App.test.ts`

**Interfaces:**
- Consumes `TrainingPlanResponse.metadata.phase_segments`
- Produces displayed plan phase timeline from backend metadata.

- [ ] **Step 1: Write timeline tests**

Assert `計畫` renders phase labels from API metadata, not fixture-only static `planPhases`.

Run: `cd frontend && npm run test -- App.test.ts -t "phase"`

Expected: FAIL if current UI only uses fixture phases.

- [ ] **Step 2: Map phase segments**

Add `mapPhaseSegments(metadata)` helper in `App.vue` or a small frontend helper file if App becomes too crowded.

- [ ] **Step 3: Render phase timeline**

Use API phase segments when present, fall back to fixture phases only for unauthenticated demo mode.

- [ ] **Step 4: Verify**

Run: `cd frontend && npm run test -- App.test.ts -t "phase"`

Expected: PASS.

---

## Stage 7: Full-System Verification

Stage goal: prove the staged work integrates without regressing existing flows.

### Task 17: Backend Contract Sweep

**Files:**
- Modify tests only if failures reveal stale expectations.

**Interfaces:**
- Consumes all backend stages.

- [ ] **Step 1: Run focused backend suites**

Run:

```bash
./.venv/bin/pytest backend/tests/unit/test_athlete_race_domain.py backend/tests/unit/test_athlete_race_api.py backend/tests/unit/test_training_plan_generation.py backend/tests/unit/test_training_plan_regeneration.py backend/tests/unit/test_agent_tools.py backend/tests/unit/test_running_companion_agent.py -q
```

Expected: PASS.

- [ ] **Step 2: Run integration backend suites**

Run:

```bash
./.venv/bin/pytest backend/tests/integration/database/test_repositories.py backend/tests/integration/application/test_agent_runtime_worker_scheduler.py -q
```

Expected: PASS.

- [ ] **Step 3: Run migration tests**

Run:

```bash
./.venv/bin/pytest backend/tests/integration/database/test_alembic_migrations.py backend/tests/integration/database/test_persistence_metadata.py -q
```

Expected: PASS.

### Task 18: Frontend Verification

**Files:**
- Modify tests only if failures reveal stale expectations.

**Interfaces:**
- Consumes all frontend stages.

- [ ] **Step 1: Run component tests**

Run:

```bash
cd frontend && npm run test -- App.test.ts
```

Expected: PASS.

- [ ] **Step 2: Run build**

Run:

```bash
cd frontend && npm run build
```

Expected: PASS.

- [ ] **Step 3: Manual smoke**

Start dev server:

```bash
cd frontend && npm run dev
```

Expected: Plan page opens, regeneration sheet opens, quota state displays, and current plan remains visible while generation is queued.

### Task 19: Documentation Alignment

**Files:**
- Modify: `docs/superpowers/specs/2026-09-17-johnny-training-plan-generation.md` only if implementation deliberately differs.
- Modify: `CONTEXT.md` only for resolved vocabulary changes.
- Modify: `docs/adr/0001-deterministic-training-plan-skeletons.md` only if the architecture boundary changes.

**Interfaces:**
- Consumes final implementation.

- [ ] **Step 1: Compare implementation against spec**

Read every heading in the spec and verify the behavior exists in code or tests.

- [ ] **Step 2: Update docs for intentional changes**

Only edit docs when implementation changes a settled decision. Do not backfill incidental implementation details into `CONTEXT.md`.

- [ ] **Step 3: Final status**

Prepare final implementation summary by stage, including any skipped verification command and reason.
