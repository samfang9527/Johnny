# Race-Aware Plans and Target Evidence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generate phase-aware plans containing every race inside the projection and derive workout HR and estimated pace from athlete evidence, with RPE as the primary fallback.

**Architecture:** The deterministic Plan Skeleton reserves race dates and owns phase, workout type, and load. A separate deterministic target policy turns optional athlete HR and pace evidence into numeric references after model output or completion repair; the LLM supplies coaching detail within those trusted limits. Race identity and target provenance survive API, persistence, and UI round trips.

**Tech Stack:** Python dataclasses, FastAPI/Pydantic, SQLAlchemy JSON workout details, pytest, Vue 3/TypeScript, Vitest.

**Spec:** `docs/superpowers/specs/2026-10-06-race-aware-plans-and-target-evidence.md`; also `openspec/changes/2026-10-03-race-aware-workload-policy/design.md`, its capability specs and outstanding coaching-review gate, `docs/adr/0001-deterministic-training-plan-skeletons.md`, and `docs/superpowers/specs/2026-09-17-johnny-training-plan-generation.md`.

## Global Constraints

- The selected Race Strategy and 16-week horizon remain unchanged. Include all athlete-owned planned/active races within the projection; preserve race entries even when the schedule is constrained.
- Extend the already implemented `race-workload-v1` policy; retain its 56-day activity capacity source, 5% development ceiling, fourth-week cutback, long-run and injury limits, and `gap`/`unknown` assessment behavior. Numerical additions require coaching review before release alongside the existing outstanding review.
- Dates, race identity, types, phase, prescribed load, numeric HR, and numeric pace are deterministic. Keep athlete-facing copy in Traditional Chinese and enum fields canonical.
- The primary race ends its projection; the existing seven-day Recovery Window follows. Do not consume a manual regeneration quota for internal model repair.
- A race edit after activation leaves the versioned Active Projection intact and surfaces the existing manual regeneration path for any in-horizon race change; keep its current quota behavior.
- A race has a prescribed distance and no invented duration. Race distance is reported separately from training minutes.
- Without a valid resting/max HR pair, RPE is primary. A pace range is optional on any running target only when pace-bearing evidence exists; every generated range records source and confidence. Rest/strength have no running pace.
- Existing saved workouts and clients without new optional fields remain readable. Avoid a database migration by keeping workout race fields in existing `WorkoutModel.details` and profile HR fields in `training_preferences`.
- Use the frontend-design and frontend-design-premium skills when implementing the UI task; preserve the app's existing visual language.

## File Map

- `backend/src/domain/training_plan.py`: `race` Workout, race identity snapshot, and optional pace source on any Workout Target.
- `backend/src/api/schemas/training_plans.py` and `backend/src/infrastructure/database/training_plan_repository.py`: optional race/target fields and JSON round trip.
- `backend/src/api/schemas/athlete_profile.py`, `backend/src/api/routes/athlete_profile.py`: optional resting/max HR setting validation and persistence.
- `backend/src/application/agent_runtime.py` and `backend/src/application/agent_tools.py`: load all in-horizon races, pass trusted skeleton and target evidence, validate and save model output.
- `backend/src/application/training_plan_generation.py` and `backend/src/application/training_workload_policy.py`: race reservation, phase-specific selection, date-aware taper/local race windows, and actual training-minute accounting.
- `backend/src/application/training_targets.py`: HR-reserve zones, pace evidence, RPE fallback, source/confidence, and recursive step normalization.
- `backend/src/infrastructure/llm/local_gateway.py` and `backend/src/infrastructure/llm/openai_gateway.py`: race-aware local output and tool schema; prompt in `agent_runtime.py`.
- `frontend/src/types.ts` and `frontend/src/App.vue`: HR settings, race detail, and target reference display.
- Existing focused backend and frontend test modules: behavior and round-trip regressions; no duplicate implementation-mirroring tests.

## Review Focus

1. Two Race Goals on the same date remain distinct; validation keys by date plus goal ID, and an activity is not auto-matched ambiguously (Tasks 1, 3, 5).
2. A midweek target race and a taper boundary crossing a week never receive an ordinary long run or pre-taper duration on race/taper dates (Tasks 3, 4).
3. A partial HR pair, max HR below resting HR, or clearing either field yields RPE-primary workouts and no numeric HR range (Tasks 2, 6, 7).
4. A goal time without measured pace is visibly low-confidence and goal-derived; mileage alone yields no invented numeric pace (Tasks 6, 7).
5. A missing or malformed model race workout is repaired as the same race with exact distance, name, and ID; a valid neighboring week remains intact (Task 5).

---

### Task 1: Race workout and optional target evidence in the saved domain

**Files:** Modify `backend/src/domain/training_plan.py`, `backend/src/api/schemas/training_plans.py`, `backend/src/infrastructure/database/training_plan_repository.py`; test `backend/tests/unit/test_training_plan_domain.py` and `backend/tests/unit/test_activity_health_domain.py`; create `backend/tests/unit/test_training_plan_race_persistence.py` for a focused SQLite round trip.

**Interfaces:** `Workout.create(..., race_goal_id: str | None = None, race_name: str | None = None, race_priority: str | None = None) -> Workout`; `WorkoutTarget(..., pace_source: str | None = None)`, with existing `pace_range_seconds_per_km` and `confidence` valid for any target kind. A canonical `zone` may remain on an RPE/HR target to preserve step intent. The `race` type requires a positive planned distance and no invented duration; other workout types have no race fields. Persist race fields in `WorkoutModel.details`.

- [ ] Write tests asserting race identity/name/priority/distance survive domain payload and SQL round trip, legacy workout payloads still parse, an RPE target may carry a sourced estimated pace range, and two same-day races do not yield a guessed activity match.
- [ ] Run `env PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest -q backend/tests/unit/test_training_plan_domain.py backend/tests/unit/test_activity_health_domain.py backend/tests/unit/test_training_plan_race_persistence.py`; verify new assertions fail on missing race/pace-source interfaces.
- [ ] Add domain validation, canonical race naming, API fields, and repository JSON mapping without a migration.
- [ ] Re-run `env PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest -q backend/tests/unit/test_training_plan_domain.py backend/tests/unit/test_activity_health_domain.py backend/tests/unit/test_training_plan_race_persistence.py`; expect the new and legacy round trips to pass.
- [ ] Commit this task's files with `feat: represent race workouts and pace evidence`.

### Task 2: Athlete HR settings

**Files:** Modify `backend/src/api/schemas/athlete_profile.py`, `backend/src/api/routes/athlete_profile.py`, `backend/src/application/agent_tools.py`; test `backend/tests/unit/test_athlete_race_api.py` and `backend/tests/unit/test_agent_tools.py`.

**Interfaces:** Profile request/response add optional `resting_heart_rate_bpm: int | None` and `max_heart_rate_bpm: int | None`. Store them in `AthletePreferences.training_preferences` as with threshold pace. Require positive values and `max > resting` when both exist; incomplete pairs may be saved but must never produce numeric HR zones. Preserve clear-on-null behavior.

- [ ] Write tests for save/read/clear, incomplete pairs, reversed pair rejection, and `getAthleteContext` profile serialization.
- [ ] Run `env PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest -q backend/tests/unit/test_athlete_race_api.py backend/tests/unit/test_agent_tools.py`; confirm failures on missing HR fields or validation.
- [ ] Implement schema, route translation, response mapping, and trusted context serialization.
- [ ] Re-run the same two test modules; expect HR round trips and existing threshold-pace behavior to pass.
- [ ] Commit with `feat: store athlete heart rate settings`.

### Task 3: Reserve all in-horizon races in the Plan Skeleton

**Files:** Modify `backend/src/application/agent_runtime.py` and `backend/src/application/training_plan_generation.py`; test `backend/tests/unit/test_training_plan_generation.py` and `backend/tests/unit/test_agent_runtime_contracts.py`.

**Interfaces:** Define immutable `PlanRace(race_goal_id: str, name: str, race_date: date, distance_meters: int, priority: str, is_target: bool, goal_intent: str | None)`. Extend `build_plan_skeleton(..., races: Sequence[PlanRace] = ()) -> PlanSkeleton`. `SkeletonWorkout` gains optional race ID/name/priority and `focus_zone: str | None`. Runtime loads future goals without the selected-ID-only context filter, chooses the selected goal as before, then passes planned/active goals in `[starts_on, ends_on]`.

- [ ] Write tests for a weekday secondary race, off-day tune-up, distant target with supporting race in the first 16 weeks, explicit maintenance containing a race but no target taper, cancelled/completed exclusion, same-date races, max-runs overflow, and selected target exactly once.
- [ ] Run `env PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest -q backend/tests/unit/test_training_plan_generation.py backend/tests/unit/test_agent_runtime_contracts.py`; confirm the race-reservation assertions fail.
- [ ] Make race dates protected; replace ordinary same-day sessions and remove optional sessions to satisfy the run cap where possible. Keep every race if protected events alone exceed the cap, and record a constrained-schedule factor.
- [ ] Re-run the same two test modules; verify no ordinary workout occupies a race date and all non-race weeks still cover the horizon.
- [ ] Commit with `feat: include in-horizon races in plan skeleton`.

### Task 4: Phase-specific training and race-aware workload

**Files:** Modify `backend/src/application/training_plan_generation.py` and `backend/src/application/training_workload_policy.py`; test `backend/tests/unit/test_training_plan_generation.py` and `backend/tests/unit/test_training_workload_policy.py`.

**Interfaces:** Keep `build_plan_skeleton` as the public entry point. Phase and local-event rules are pure helpers inside the generation module; `WorkloadPrescription.weeks` contains actual training minutes after date-based adjustments. Bump `POLICY_VERSION` to `race-workload-v2`.

- [ ] Write tests for the spec's exact base/build/peak quality rotation and focus zones, short/long target taper dates, no final-three-day quality, taper reduction across a midweek boundary, supporting-race windows, race-over-capacity warning, and race exclusion from training-minute totals.
- [ ] Run `env PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest -q backend/tests/unit/test_training_plan_generation.py backend/tests/unit/test_training_workload_policy.py`; confirm the current repeated weekly pattern and race-day long run fail them.
- [ ] Implement phase-aware quality selection, target-race taper by date, local supporting-race windows, hard-session accounting, and post-adjustment weekly totals/assessment. Preserve existing capacity/injury limits and continuity with prior long runs.
- [ ] Verify the original 40 km/25 km-week reproduction still obeys development and long-run limits and names a preparation gap where applicable; ensure race distance never becomes a fabricated duration during assessment or step validation.
- [ ] Re-run the same two test modules; verify no race is dropped even when local protection windows overlap.
- [ ] Commit with `feat: phase and race-aware workload progression`.

### Task 5: Enforce race identity through model output and completion repair

**Files:** Modify `backend/src/application/agent_runtime.py`, `backend/src/application/agent_tools.py`, `backend/src/application/training_plan_generation.py`, `backend/src/infrastructure/llm/local_gateway.py`, `backend/src/infrastructure/llm/openai_gateway.py`; test `backend/tests/unit/test_agent_tools.py`, `backend/tests/unit/test_running_companion_agent.py`, and `backend/tests/unit/test_training_plan_generation.py`.

**Interfaces:** Skeleton/tool payloads include `race_goal_id` for race workouts and `focus_zone` for key sessions. Match generated workouts to skeleton by `(scheduled_for, race_goal_id)`; copy race name/priority from trusted skeleton. Extend `_template_steps(workout_type, planned_duration_minutes, planned_distance_meters=None, focus_zone=None)` so a race fallback produces a distance-based `free_run` step.

- [ ] Write tests for local gateway race output, RPE 6 controlled/complete and RPE 8 performance defaults, a missing/misidentified/model-altered race, same-day races, valid-week preservation during repair, and exact race distance after fallback.
- [ ] Run `env PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest -q backend/tests/unit/test_agent_tools.py backend/tests/unit/test_running_companion_agent.py backend/tests/unit/test_training_plan_generation.py`; confirm race output/validation/repair failures.
- [ ] Update prompt and tool schema, trusted-skeleton parsing, validation, local and fallback generation, and repair. Require race steps to cover exactly the event distance and key work steps to carry the skeleton focus zone before target normalization; keep race metadata model-independent.
- [ ] Re-run the same three test modules; expect every generated or repaired race to match the skeleton and all legacy non-race generation tests to pass.
- [ ] Commit with `feat: preserve races through generation and repair`.

### Task 6: Deterministic HR and pace evidence policy

**Files:** Modify `backend/src/application/training_targets.py`, `backend/src/application/agent_runtime.py`, `backend/src/application/agent_tools.py`; test `backend/tests/unit/test_training_targets.py` and `backend/tests/unit/test_agent_tools.py`.

**Interfaces:** Introduce `TargetProfile` with optional HR pair, pace source/confidence, and zone ranges; `build_target_profile_from_payloads(profile_payload: dict | None, selected_race_payload: dict | None, recent_activity_payloads: tuple[dict, ...], prior_plan_payload: dict | None) -> TargetProfile`; `enrich_workout_steps(steps: tuple[WorkoutStep, ...], *, workout_type: str, target_profile: TargetProfile) -> tuple[WorkoutStep, ...]`. `TargetProfile.from_payload` accepts the old `pace_profile` trusted-context shape for already queued runs.

- [ ] Write tests for the spec's exact HR-reserve bands and RPE-to-zone map, RPE primary with absent/partial HR, HR-primary sustained work with a valid pair, RPE-primary hill/short/race work, and pace on RPE and HR targets. Cover threshold pace, matched completed race within 5% distance, three qualifying paired easy runs, goal-derived low confidence and 20% widening, and no numeric pace from mileage or one unmatched run.
- [ ] Run `env PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest -q backend/tests/unit/test_training_targets.py backend/tests/unit/test_agent_tools.py`; confirm the current pace-to-RPE conversion and missing HR profile fail the intended assertions.
- [ ] Implement the versioned target policy, recursive repeat handling, canonical-zone retention on RPE/HR targets, and deterministic numeric overwrite after model output and repair. Reject impossible values and never convert a goal time into a measured result.
- [ ] Re-run the same two test modules and `backend/tests/unit/test_training_plan_race_persistence.py`; verify source/confidence survive saved-plan serialization.
- [ ] Commit with `feat: derive workout targets from athlete evidence`.

### Task 7: Show HR settings, race workouts, and target references

**Files:** Modify `frontend/src/types.ts` and `frontend/src/App.vue`; test `frontend/src/App.test.ts` and `frontend/src/Stage7.test.ts`; update `DESIGN.md` only if the new UI behavior requires project design guidance.

**Interfaces:** Athlete settings expose/clear both HR values. Workout rendering uses the saved race name/priority and event distance. `formatWorkoutTarget` shows primary RPE/HR, optional `預估配速`, and source/confidence for every running target kind; hill/technical pace is labelled as reference. Existing historical payloads with no new fields still render.

- [ ] Write component tests for HR save/clear/errors, target/secondary/tune-up race cards, RPE plus estimated pace, HR plus estimated pace, RPE-only missing evidence, narrow viewport text wrapping, and a regeneration reminder when any remaining in-horizon race is added/moved/cancelled/deleted.
- [ ] Run `cd frontend && npm test -- App.test.ts Stage7.test.ts` and confirm the new behavior fails before changes.
- [ ] Implement fields, validation, labels, responsive workout detail, and the existing regeneration reminder for every in-horizon race edit. Do not claim a newly saved race has entered the active plan before regeneration.
- [ ] Re-run focused tests, `cd frontend && npm run build`, and `cd frontend && npm run verify:tokens`; expect all pass.
- [ ] Commit with `feat: show race and target evidence in plan UI`.

### Task 8: Cross-path verification and release documentation

**Files:** Create `backend/tests/integration/application/test_race_aware_generation_flow.py`; update `CONTEXT.md` only for new domain terms and update the plan-generation verification runbook if it describes target/race behavior.

**Interfaces:** Drive the same synthetic athlete through local generation, trusted tool save, repository read, and API serialization. Verify one target plus a secondary and tune-up, a race outside preferred weekdays, HR/RPE paths, and deterministic completion repair; inspect both model-backed and local gateway contracts without a paid call.

- [ ] Write the cross-path test using a synthetic athlete and in-memory/SQLite stores; assert every race ID/date/distance and target source survives the full path.
- [ ] Run `env PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest -q backend/tests/integration/application/test_race_aware_generation_flow.py` once red against any remaining integration gap; fix only the failing seam.
- [ ] Run `env PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest -q backend/tests`, frontend unit tests, frontend build, and token check; record actual counts and any infrastructure-only skips. Re-run the existing race-aware workload fixtures and note that numerical-policy coaching review remains open before release.
- [ ] Search for stale race/target enum lists and run `git diff --check`; resolve only issues introduced by this plan.
- [ ] Commit the final integration/documentation task and summarize remaining limits, especially uncertain pace estimates and lack of live provider verification.
