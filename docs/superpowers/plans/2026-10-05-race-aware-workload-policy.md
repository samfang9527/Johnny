# Race-Aware Workload Policy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generate race Plan Versions whose prescribed workload reflects recent running capacity and known race demands, and show a preparation gap when the feasible plan falls short.

**Architecture:** Keep Johnny's deterministic ownership of the Plan Skeleton. A pure workload policy derives a capacity snapshot, weekly prescription, and preparation assessment; the existing skeleton builder assigns exact workouts from that prescription. The LLM and local provider enrich the same trusted skeleton, and `createTrainingPlan` validates and persists it. Optional Race Goal fields and a public assessment flow through existing JSON metadata and API responses.

**Tech Stack:** Python/FastAPI/Pydantic/SQLAlchemy/Pytest; Vue 3/TypeScript/Vitest; OpenSpec.

**Spec:** `openspec/changes/2026-10-03-race-aware-workload-policy/design.md` and `openspec/changes/2026-10-03-race-aware-workload-policy/specs/*/spec.md`.

## Global Constraints

- Work only in `openspec/changes/2026-10-03-race-aware-workload-policy` until the change is complete; read its five artifact types before implementation.
- The product owner approved `design.md` and native implementation on 2026-10-05. The numeric thresholds remain versioned provisional defaults; separate coaching review is a release check, tracked in the change's tasks.
- Preserve ADR-0001: deterministic scheduling, phase coverage, and completeness; the model enriches Workout Steps, purposes, and Coach Notes.
- Preserve existing 16-week race and four-week maintenance horizons, Regeneration Quota, hard-session spacing, provider pinning, and historical Plan Versions.
- Old Race Goals, old Plan Versions, and direct manual plan creation remain readable and valid.
- Athlete-facing copy is Traditional Chinese. `on_track` describes a policy reference, never guaranteed race completion or medical clearance.
- Do not make a paid OpenAI call as part of routine tests. Verify the OpenAI request with a fake client and the production queue/worker with the local provider.
- Keep untrusted model arguments separate from trusted policy context. Do not expose private activity/source evidence in training-plan API responses.
- Backend commands below run from the repo root with `PYTHONPATH=backend .venv/bin/python -m pytest`; frontend commands use `npm --prefix frontend`.

## File Map

| Responsibility | Files |
|---|---|
| Race Goal course fields | `backend/src/domain/athlete_race.py`, `backend/src/infrastructure/database/athlete_race_repository.py`, `backend/src/api/schemas/races.py`, `backend/src/api/routes/races.py`, `backend/src/application/agent_tools.py` |
| Capacity and policy | New `backend/src/application/training_workload_policy.py`; `backend/src/application/agent_runtime.py` loads complete activity evidence |
| Skeleton and validation | `backend/src/application/training_plan_generation.py`, `backend/src/application/agent_tools.py` |
| Provider requests | `backend/src/application/agent_runtime.py`, `backend/src/infrastructure/llm/local_gateway.py`, `backend/src/infrastructure/llm/openai_gateway.py` tests |
| Plan response | `backend/src/api/schemas/training_plans.py`, `backend/src/api/routes/training_plans.py` |
| Race entry and plan display | `frontend/src/components/RaceGoalModal.vue`, `frontend/src/raceGoalForm.ts`, `frontend/src/types.ts`, `frontend/src/App.vue` |
| Documentation | The active OpenSpec specs for touched capabilities, `CONTEXT.md`, and this change's `tasks.md` |

## Review Focus

These five easy-to-miss cases each have a test in the owning task:

1. A 56-day activity window with more than 20 entries must use the full user-scoped set and exclude cycling, strength work, and duplicate activity IDs (Task 2).
2. Activity timestamps near an athlete-local week boundary must group into the correct week, including a timezone offset change (Task 2).
3. A cancelled race, missing Athlete Baseline, or activity-read error must not produce invented high-confidence capacity or an `on_track` assessment (Tasks 2 and 5).
4. A valid planned duration with model steps covering only a small fraction of it must trigger repair, and persisted fallback steps must fill that duration (Task 6).
5. An old Race Goal or manual/legacy plan lacking the new fields must still load in the API and frontend, without a fabricated assessment (Tasks 1 and 7).

---

### Task 1: Race Goal course contract

**Files:** Modify `backend/src/domain/athlete_race.py`, `backend/src/infrastructure/database/athlete_race_repository.py`, `backend/src/api/schemas/races.py`, `backend/src/api/routes/races.py`, `backend/src/application/agent_tools.py`; test `backend/tests/unit/test_athlete_race_domain.py`, `backend/tests/unit/test_athlete_race_api.py`, `backend/tests/integration/database/test_repositories.py`.

**Interfaces:** Extend `RaceGoal.create(...)`, `RaceGoalCreateRequest`, `RaceGoalResponse`, `_race_goal_payload(...)` with `ascent_meters: float | None`, `descent_meters: float | None`, `terrain_difficulty: Literal['runnable','mixed','technical'] | None`, `cutoff_seconds: int | None`, and `goal_intent: Literal['complete','perform'] | None`. Use existing race `metadata_json`; null legacy values are explicit. Negative ascent/descent, nonpositive cutoff, and unsupported enum values fail validation.

- [ ] **Step 1: Write failing tests.** `test_race_goal_accepts_optional_course_fields_and_rejects_invalid_values`, `test_race_api_round_trips_course_fields_and_accepts_legacy_request`, and `test_race_repository_reads_missing_course_metadata_as_null`. Assert the tool context payload includes every field and a race name containing “trail” does not fabricate terrain.
- [ ] **Step 2: Run those tests.** `PYTHONPATH=backend .venv/bin/python -m pytest backend/tests/unit/test_athlete_race_domain.py backend/tests/unit/test_athlete_race_api.py backend/tests/integration/database/test_repositories.py -q` must fail on missing fields/assertions.
- [ ] **Step 3: Implement** the five fields and validation in the files above, saving them in the existing race metadata JSON and returning them through the API and `getAthleteContext` tool.
- [ ] **Step 4: Rerun the same command.** Expect all selected tests to pass.
- [ ] **Step 5: Commit** the focused race contract and tests as `feat: capture race course demands`.

### Task 2: Evidence-based capacity snapshot

**Files:** Create `backend/src/application/training_workload_policy.py`; modify `backend/src/application/agent_runtime.py`; test new `backend/tests/unit/test_training_workload_policy.py` and `backend/tests/unit/test_running_companion_agent.py`.

**Interfaces:** Define frozen `CapacitySnapshot(source: str, confidence: str, weekly_minutes: int | None, weekly_distance_km: float | None, recent_long_run_minutes: int | None, observation_start: date, observation_end: date, activity_count: int, missing_dimensions: tuple[str, ...])` and `derive_capacity_snapshot(*, profile: dict, activities: Sequence[dict], anchor: date) -> CapacitySnapshot`. Activity source is `activities`, `stated_mileage`, or `missing`; confidence is `high` only under the design's eight-run/three-week/14-day rule. Add private provenance as a separate result field if needed; do not put activity IDs in the public assessment. Deduplicate by persisted `id`, falling back to `(source, source_activity_id)` where necessary.

- [ ] **Step 1: Write failing tests.** Pin the four complete calendar weeks, median weekly minutes, longest run in the last 28 days, athlete-local grouping, duplicate exclusion, sport filtering, stated-mileage fallback at six minutes/km, zero/missing fallback, and a 25-activity fixture that includes entries beyond the old 20-record cutoff.
- [ ] **Step 2: Run the policy and agent tests.** `PYTHONPATH=backend .venv/bin/python -m pytest backend/tests/unit/test_training_workload_policy.py backend/tests/unit/test_running_companion_agent.py -q` must fail on the new snapshot assertions.
- [ ] **Step 3: Implement** `derive_capacity_snapshot(...)`. In `_training_plan_generation_preload_context`, query `getRecentActivities` once for all 56 days with no `limit`; take the most recent 20 in the past 28 days only for the model's compact activity slice. If activity access fails, record missing evidence; if the required athlete/race context fails, fail the run. Do not change the read tool's general API.
- [ ] **Step 4: Rerun the same tests.** Expect both files to pass, including the more-than-20-record case.
- [ ] **Step 5: Commit** as `feat: derive training capacity from complete recent activity`.

### Task 3: Versioned workload prescription and assessment

**Files:** Modify `backend/src/application/training_workload_policy.py`; test `backend/tests/unit/test_training_workload_policy.py`.

**Interfaces:** Add frozen `RaceDemand(distance_meters, race_date, target_finish_seconds, ascent_meters, descent_meters, terrain_difficulty, cutoff_seconds, goal_intent)`, `WorkloadWeek(week_index, target_minutes, long_run_minutes, phase, terrain_focus)`, `PreparationAssessment(status, factors, explanation_zh, policy_version)`, and `WorkloadPrescription(weeks, assessment, policy_version)`. Implement `build_workload_prescription(*, capacity: CapacitySnapshot, race: RaceDemand | None, starts_on: date, ends_on: date, phase_segments: Sequence[dict], max_runs_per_week: int, max_hard_sessions_per_week: int, injury_status: str, prior_plan: Mapping[str, Any] | None = None) -> WorkloadPrescription` and `assess_preparation(*, capacity: CapacitySnapshot, race: RaceDemand | None, starts_on: date, ends_on: date, weekly_minutes: Sequence[int], long_run_minutes: Sequence[int], terrain_session_count: int, policy_version: str) -> PreparationAssessment`. The first function estimates an assessment; the skeleton builder calls the second with its actual scheduled totals. Set the policy version to `race-workload-v1`. If no recent long run is recorded, initialize it at `min(90, round(0.4 * weekly_minutes))`; missing weekly minutes retain the 30-minute default. Treat `current`/`recent` injury as 80% of starting volume with no build until status changes; retain the existing 65% taper factor. Races outside the calibrated 30–50 km band keep their existing duration ceilings and cannot receive `on_track` from this policy version.

- [ ] **Step 1: Write failing tests.** Assert `weeks[1].target_minutes <= round(weeks[0].target_minutes * 1.05)`, `weeks[3].target_minutes == round(weeks[2].target_minutes * 0.85)`, a later development week resumes above the cutback, each long run is at most 110% of its prior anchor and 50% of weekly minutes, and a 30–50 km long run can reach but never exceed 180 minutes. Pin the 65% taper, injury hold/reduction, the 300/150 `gap` reference, known-gap precedence over unknown, and no `on_track` for low-confidence or uncalibrated >50 km input. Assert known mixed/technical terrain requests two `terrain_focus` weeks in the last eight development weeks when Hard Session Capacity permits, and records `terrain_exposure` otherwise. Test a short horizon and three-day limit.
- [ ] **Step 2: Run the policy tests.** `PYTHONPATH=backend .venv/bin/python -m pytest backend/tests/unit/test_training_workload_policy.py -q` must fail on the missing policy behavior.
- [ ] **Step 3: Implement** the pure function and typed results. Keep capacity estimates, race references, and feasible workload separate. Use the approved heuristic values from `design.md`; do not interpret them as medical thresholds. Treat unknown ascent/descent evidence honestly and do not convert ascent into flat running minutes.
- [ ] **Step 4: Rerun the policy tests.** Expect all policy tests to pass.
- [ ] **Step 5: Commit** as `feat: prescribe versioned race workload and preparation assessment`.

### Task 4: Make the Plan Skeleton consume the prescription

**Files:** Modify `backend/src/application/training_plan_generation.py`; test `backend/tests/unit/test_training_plan_generation.py` and `backend/tests/unit/test_training_plan_generation_domain.py`.

**Interfaces:** Extend `build_plan_skeleton(...)` with optional `capacity_snapshot: CapacitySnapshot | None`, `race_demand: RaceDemand | None`, and `prior_plan: Mapping[str, Any] | None`. Keep existing callers valid by deriving a low-confidence snapshot from their stated-mileage arguments. Add `workload_prescription: WorkloadPrescription | None` to `PlanSkeleton`. Allocate each `WorkloadWeek` target over its scheduled days so the sum of workout durations matches its target to rounding; use the prescribed long-run minutes on the preferred long-run day. Reassess the actual scheduled totals and hill-session count with `assess_preparation(...)` before returning the skeleton. Preserve dates, hard-session limit, safe spacing, phases, and partial-week handling.

- [ ] **Step 1: Write failing tests.** Reproduce the 40 km / 25 km-week / three-day case: `assert max(long_run_minutes) > 70` and `assert assessment.status == 'gap'` when 300/150 is infeasible. Assert a supported 50 km-week athlete can exceed the former 120-minute long-run cap, intermediate and advanced with identical history have identical starting load, and a >50 km race does not receive the 40 km `on_track` reference. Assert `terrain_focus` weeks produce hill workouts only when the existing Hard Session Capacity and spacing permit them; otherwise the assessment records the terrain gap. Retain spacing and existing phase tests.
- [ ] **Step 2: Run the skeleton tests.** `PYTHONPATH=backend .venv/bin/python -m pytest backend/tests/unit/test_training_plan_generation.py backend/tests/unit/test_training_plan_generation_domain.py -q` must fail on the new expectations.
- [ ] **Step 3: Implement** the prescription adapter in `build_plan_skeleton(...)`; replace `_planned_duration` for generated race workloads. Update earlier tests that intentionally asserted the superseded formula, while keeping tests for valid old invariants.
- [ ] **Step 4: Rerun both test files.** Expect pass; inspect the printed 40 km fixture to confirm actual skeleton durations match the policy report.
- [ ] **Step 5: Commit** as `feat: generate race skeletons from workload prescription`.

### Task 5: Feed the policy to local and OpenAI generation

**Files:** Modify `backend/src/application/agent_runtime.py`, `backend/src/infrastructure/llm/local_gateway.py`; test `backend/tests/unit/test_running_companion_agent.py`, `backend/tests/unit/test_local_gateway.py`, `backend/tests/unit/test_openai_gateway.py`.

**Interfaces:** `_training_plan_generation_preload_context(...)` places `workload_policy_version`, `preparation_assessment`, and a compact `workload_prescription` beside `plan_skeleton` in `ModelRequest.context`. `_inject_training_plan_trusted_context(...)` copies these trusted fields into write-tool arguments. The OpenAI tool schema remains structurally unchanged; `openai_gateway._input_messages(...)` already serializes request context. The local gateway builds steps from exact skeleton durations.

- [ ] **Step 1: Write failing tests.** Verify the same policy-derived context appears for local and fake OpenAI requests; the prompt tells the model to fill steps within fixed dates/types/durations and explain gap factors; an activity-read failure yields low confidence; a required athlete/race read failure fails without creating a plan; local interval/hill/tempo steps remain inside the prescribed duration.
- [ ] **Step 2: Run the gateway and runtime tests.** `PYTHONPATH=backend .venv/bin/python -m pytest backend/tests/unit/test_running_companion_agent.py backend/tests/unit/test_local_gateway.py backend/tests/unit/test_openai_gateway.py -q` must fail on new expectations.
- [ ] **Step 3: Implement** context, trusted copying, prompt changes, and local duration-based steps. Keep provider/model pinning and the existing single repair attempt.
- [ ] **Step 4: Rerun the same files.** Expect pass without a network call.
- [ ] **Step 5: Commit** as `feat: give generators trusted workload prescription`.

### Task 6: Validate executable workload and expose assessment safely

**Files:** Modify `backend/src/application/training_plan_generation.py`, `backend/src/application/agent_tools.py`, `backend/src/api/schemas/training_plans.py`, `backend/src/api/routes/training_plans.py`; test `backend/tests/unit/test_training_plan_generation.py`, `backend/tests/unit/test_agent_tools.py`, `backend/tests/unit/test_running_companion_agent.py`, `backend/tests/unit/test_product_workflow_api.py`.

**Interfaces:** Keep exact date/type/phase/duration skeleton validation and the existing 30-second upper tolerance. For duration-based Workout Steps, require executable duration of at least 90% of planned minutes; account for repeat blocks and distance-only steps using the existing conservative conversion. Persist trusted `workload_policy_version` and public `preparation_assessment` in plan metadata, with private source and repair details under `internal`. Add `preparation_assessment: dict | None` to `TrainingPlanResponse` and strip private `metadata.internal` from API output; direct manual plan writes do not gain a fabricated assessment.

- [ ] **Step 1: Write failing tests.** A 60-minute workout with 10 minutes of steps must be repaired; a 60-minute workout with 55 minutes of valid steps must pass; over-budget repeat blocks must fail; repaired and fallback steps must fill the prescribed duration. Verify trusted assessment wins over model metadata, the policy version survives persistence, private activity IDs do not appear in API JSON, and old/manual plans still return successfully.
- [ ] **Step 2: Run focused generation, tool, and API tests.** `PYTHONPATH=backend .venv/bin/python -m pytest backend/tests/unit/test_training_plan_generation.py backend/tests/unit/test_agent_tools.py backend/tests/unit/test_running_companion_agent.py backend/tests/unit/test_training_plan_generation_domain.py backend/tests/unit/test_product_workflow_api.py -q` must fail on new assertions.
- [ ] **Step 3: Implement** lower-bound validation, policy-aligned repair/fallback, trusted metadata, and public API mapping. Preserve the existing one model repair attempt and transactional activation boundary.
- [ ] **Step 4: Rerun the same focused command.** Expect pass and no private `internal` metadata in serialized API responses.
- [ ] **Step 5: Commit** as `feat: validate prescribed workout load and publish plan assessment`.

### Task 7: Race entry and Plan view

**Files:** Modify `frontend/src/components/RaceGoalModal.vue`, `frontend/src/raceGoalForm.ts`, `frontend/src/types.ts`, `frontend/src/App.vue`; test `frontend/src/raceGoalForm.test.ts`, `frontend/src/App.test.ts`.

**Interfaces:** `RaceGoalCreatePayload` gains nullable/optional `ascent_meters`, `descent_meters`, `terrain_difficulty`, `cutoff_seconds`, and `goal_intent`; `TrainingPlanResponse` frontend type gains optional `preparation_assessment`. Form labels use metric units and allow truly unknown values. The Plan view renders `status`, `explanation_zh`, and factors near the selected race, without suggesting medical clearance.

- [ ] **Step 1: Write failing tests.** Submit a 40 km trail race with ascent and cutoff and assert exact request JSON; submit a legacy race with blank optional fields; reject invalid negative/nonpositive values. Render `gap`, `unknown`, and legacy plan fixtures and assert Traditional Chinese copy plus accessible status semantics.
- [ ] **Step 2: Run frontend tests.** `npm --prefix frontend test -- src/raceGoalForm.test.ts src/App.test.ts` must fail on new assertions.
- [ ] **Step 3: Implement** the optional inputs, request mapping, read display, assessment display, and type changes. Keep layout and regeneration polling consistent with current Plan behavior.
- [ ] **Step 4: Rerun tests and build.** `npm --prefix frontend test -- src/raceGoalForm.test.ts src/App.test.ts` and `npm --prefix frontend run build` must pass.
- [ ] **Step 5: Commit** as `feat: show race course and preparation assessment`.

### Task 8: Production-path verification and documentation

**Files:** Modify `backend/tests/integration/application/test_agent_runtime_worker_scheduler.py`, active OpenSpec capability specs, `CONTEXT.md`, and `openspec/changes/2026-10-03-race-aware-workload-policy/tasks.md`; add a focused fixture/test file if the existing integration file is unwieldy.

**Interfaces:** Exercise `POST /api/v1/training-plans/regenerations` → queued local run → production worker dispatch → saved Active Projection → API read. Assert that the saved plan has policy version, complete weeks, executable steps, and the expected 40 km `gap`. Use a disposable test database/session, not the developer's existing athlete records. Verify superseding preserves historical workouts.

- [ ] **Step 1: Write the failing production-path test.** Include a 40 km Race Goal, an Athlete Baseline of 25 km/week, three training days, and controlled recent activities; assert the final Active Projection differs from the original short skeleton and exposes the gap. Add a second test that invalid policy/profile input leaves the prior Active Projection active.
- [ ] **Step 2: Run the integration test.** `PYTHONPATH=backend .venv/bin/python -m pytest backend/tests/integration/application/test_agent_runtime_worker_scheduler.py -q` must fail on the new assertions before integration fixes.
- [ ] **Step 3: Complete** any wiring corrections, update active OpenSpec specs and `CONTEXT.md` using the approved domain language, and resolve older LLM-ownership wording in the relevant active spec. Mark this change's tasks only after each task's tests pass.
- [ ] **Step 4: Verify.** Run `PYTHONPATH=backend .venv/bin/python -m pytest backend/tests -q`, `npm --prefix frontend test`, `npm --prefix frontend run build`, `openspec validate 2026-10-03-race-aware-workload-policy --strict`, and `git diff --check`. Report any database-dependent test skipped by the local environment explicitly.
- [ ] **Step 5: Commit** as `test: verify race-aware workload through regeneration` and make the complete branch reviewable.
