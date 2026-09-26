# Training Plan Generation: Stage 7 Verification

## Verdict

**Stage 7 complete on 2026-09-27.** All acceptance findings and scoped review
follow-ups are closed. Independent spec and quality reviews passed, including
the whole-stage integration review and its Target/layout follow-ups. No next
stage was started. Live-environment limits below remain explicit.

Initial verification on 2026-09-26 used `163dbc5` (the merged Start Line UI). Initial checks ran
at `06345e1`; backend source did not change between these revisions. This report
records the initial findings and their follow-up. The spec now explicitly records
completion-day quota attribution, delayed background start dates, and the already
accepted Recovery Window presentation; the ADR boundary remains unchanged.

## Repair Verification

- Activation / Today / strategy-default repairs passed independent spec and
  quality review. Fifteen real-persistence regressions cover savepoint rollback,
  successive supersession, preserved workout completion, and lineage guards.
- Controller reran the full backend suite after generation repairs:
  **476 passed, 1 skipped, 1 warning** in 8.83 seconds. The skip requires a live
  `JOHNNY_TEST_DATABASE_URL`; SQLite results do not certify PostgreSQL.
- Backend generation repairs address baseline/distance budgets, conservative
  missing-baseline templates, far-future base-only phases, one model repair before
  local deterministic completion, numeric Target normalization, canonical names,
  and successful activation-day quota. The follow-up mixed-unit executable-load
  bound recursively accounts for work/recovery/repeats independently of model
  pace claims; empty aggregate names now preserve valid original weeks and
  trusted workout IDs through incomplete or absent model repair. Independent
  final review confirms those two findings are addressed. It found an additional
  heart-rate Target gap: zone-only Targets lacked numeric validation and the
  consumer hid existing RPE fallback. Backend numeric bpm/RPE validation and
  normalization are covered in the 476-pass run; independent Target/consumer
  re-review passed. Earlier 467-pass results predate this heart-rate follow-up.
- Frontend review follow-up adds shared snapshot freshness, session-generation
  guards and stale-Today retry/degraded state. Controller independently reran
  **112 passed** in 6.48 seconds, production build, token verification and a
  zero-finding premium audit after all fixes. Deferred-response/midnight/failure
  and HR rendering regressions are included. Scoped review confirms the async
  findings and subsequent mobile phase-stop sizing regression are addressed.
- Authenticated fixture browser smoke passed: canonical maintenance timeline and
  main journey; no fixture Build when no active plan; recovery day 3/7 with seven
  inclusive dates and Asia/Taipei; old plan preserved during generation; automatic
  switch after the thirteenth poll; exhausted quota with disabled confirmation
  and athlete-local midnight availability; Escape restores trigger focus.
- Desktop, 390x844 and 320x844 authenticated fixture checks cover five-phase and
  recovery states. Mobile intro/recovery content stays bounded; phase tracks keep
  compatible minimum widths in their own horizontal scroller. Rendered text
  lines fit and all five stops remain separate. Controller independently checked
  final 320px stop widths (144px each) and non-overlap; the implementer verified
  scrolling through the last phase and desktop dimensions. The pre-existing
  320px app minimum can exceed the 309px client area with a vertical scrollbar;
  this was not represented as zero document overflow at that viewport.
- All temporary fixture servers and browser tabs were stopped/closed after
  verification. No user services, dependencies, external duplicate files, or
  historical workout completion records were removed.

## Finding Disposition

| Findings | Resolution |
| --- | --- |
| F1/F2/F5 | Trusted Today lineage, transactional activation/worker rollback, current future strategy default |
| F4/F6/F7/F8 | Baseline/distance skeleton, one model repair and valid-week salvage, normalized numeric Targets, canonical names |
| F3/F9 and Recovery Window | Bounded continuing observation, canonical metadata journey, explicit seven-day recovery presentation |
| R1/R2/R3 | Shared read freshness, session/date guards, degraded Today and current-day retries |
| G1/G2 | Executable mixed-unit budget checks and name-independent valid-week/UUID preservation |
| R4/S7-1 | Separate mobile scroll tracks and bounded prose; numeric HR validation plus compatible RPE rendering |

Full backend verification command (external duplicate tests are excluded):

```sh
env PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPYCACHEPREFIX=/private/tmp/johnny-task17-pycache .venv/bin/python -m pytest backend/tests --ignore-glob='* 2.py' -q --tb=short
```

## Verification Limits

- No live PostgreSQL or model-provider integration was exercised. In-memory
  model probes and SQLite rollback regressions are not substitutes for those.
- Frontend tests/build use identical source/config/package-lock in a clean
  temporary dependency installation; the original dependency-directory loading
  delay was isolated, not repaired. Temporary browser fixtures use no real user
  data and are not a deployed backend/frontend end-to-end environment.
- Volume factors, readiness gates and conservative distance accounting are V1
  product heuristics, not individualized physiological guarantees. Larger valid
  distance sessions for faster athletes may conservatively fall back to templates.
- Historical quota attribution uses the current Athlete Baseline timezone;
  timezone edits can reclassify prior completions. Legacy successes without a
  trustworthy completion timestamp cannot be charged reliably.

## Initial Verification Results

| Check | Result | Scope / limitation |
| --- | --- | --- |
| Task 17 focused backend suites | 129 passed | Domain/API, skeleton, regeneration, agent tools and runtime |
| Task 17 integration suites | 45 passed | Repository and worker/scheduler integration |
| Task 17 migrations / metadata | 15 passed | SQLite-based checks, not a live PostgreSQL deployment |
| Task 18 App component tests | 67 passed in isolated copy | Same source/config/lockfile, clean dependencies under `/private/tmp/johnny-stage7-clean`; original directory worker startup still times out |
| Task 18 production build | Passed at merged HEAD | Type checking and Vite build |
| Design token check | Passed | `npm run verify:tokens` |
| Browser smoke | Partial pass | Real frontend, isolated API fixtures; not live backend/LLM integration |
| Task 19 spec alignment | Failed acceptance | Findings below, independently audited by a subagent |

The 189 backend tests ran with `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1` and
`PYTHONPYCACHEPREFIX=/private/tmp/johnny-task17-pycache`. These command-local
settings avoided dependency/plugin discovery delays; no assertions or installed
dependencies were changed. Two FastAPI/Starlette test-client deprecation warnings
were emitted. The exact default startup commands were interrupted before test
collection, so their outcomes are not counted as passes.

Frontend worker startup failed with both forks and threads, including a run
outside the sandbox. A standalone `jsdom` import also stalled; a one-second
process sample showed `node::fs::InternalModuleStat -> uv_fs_stat -> stat`.
Dependency loading made slow progress, including a completed `parse5` import.
This establishes a local dependency-loading delay, not its underlying cause.
Do not label these attempts as failed application assertions or passing tests.

Continuation: installing the unchanged lockfile in `/private/tmp/johnny-stage7-clean`
and copying the current `src`, Vite config, and both TypeScript configs allowed
`npm run test -- App.test.ts` to complete: **67 passed in 6.47s**. This isolates
the verification workaround from the repo's existing dependencies. It does not
claim the original dependency directory has been repaired.

Browser checks confirmed the Plan page, API phase segment, race-default sheet,
maintenance selection with a race present, quota display, preservation of the
old workout during queueing, and disabled confirmation for an existing run.
Initial submit smoke ran before the UI merge; the merged UI was checked again
for sheet opening and the existing-run state. The fixture-backed main journey
contradicted the API phase segment, confirming F9. Real generation completion,
quota exhaustion, mobile layout, and live PostgreSQL were not browser-verified.

## Initial Acceptance Findings

References identify symbols as well as paths because subsequent fixes will
move lines. F1-F8 predate the UI merge; F9 was introduced by that merge.

| ID | Priority | Finding and evidence | Required regression |
| --- | --- | --- | --- |
| F1 | P1 | Today's workout is retained in storage but disappears from current reads after immediate supersession. `BuildTodayContextHandler.handle` in `backend/src/application/training_analytics.py` reads only `get_current_plan_for_user`; the new projection begins tomorrow. `applyTrainingPlansPayload` in `frontend/src/App.vue` likewise selects only the active plan. | Read Today before and after activation; today's original workout remains visible/executable and its completion history survives. |
| F2 | P1 | A caught failure after `createTrainingPlan` can leave the new plan and supersession in the transaction. `RunningCompanionAgent._run_model_workflow` in `backend/src/application/agent_runtime.py` marks failure without rolling back plan mutations; `scripts/agent_runtime.py` later commits the worker session. This is a source-supported failure path, not yet a failure-injection test result. | Use real repositories, inject failure after creation but before successful completion, and prove old projection/quota remain unchanged after worker commit. |
| F3 | P1 | `schedulePlanRegenerationPoll` in `frontend/src/App.vue` stops after 12 polls at two-second intervals, leaving the in-flight banner and stale plan indefinitely when a run finishes later. | Completion and failure after more than 12 polls must still transition correctly; cleanup on unmount remains bounded. |
| F4 | P1 | `build_plan_skeleton` in `backend/src/application/training_plan_generation.py` ignores race distance, mileage and experience. It prescribes 75 minutes for long runs and 45 for all others; missing profiles also retain the default hard-session load. Validation prevents enrichment from changing that load. | Different race distances and baseline volumes produce appropriate deterministic structures/loads; missing or weak baselines receive conservative volume and capacity without invented finish goals. |
| F5 | P2 | `TrainingPlanRegenerationService.options` always uses automatic race priority/date selection. API service wiring does not provide the current plan repository, so a still-future existing Race Strategy can be silently replaced. | Existing secondary-race strategy remains the default despite a newly added primary race; expired strategy falls back to automatic selection. |
| F6 | P2 | `CreateTrainingPlanTool.run` immediately performs deterministic Completion Repair for well-formed incomplete output. The runtime model repair path runs only on escaping errors, so the spec's first repair attempt followed by template completion is not represented for this case. | Incomplete output follows the agreed repair order, preserves valid weeks, and records the actual repairs; settle the intended first-pass boundary without silently changing the spec. |
| F7 | P2 | Replacement steps are created after target enrichment. Their pace-kind targets may contain only zone plus RPE; the frontend pace renderer ignores that numeric RPE. | Repaired weak-baseline tempo/interval targets show executable numeric effort in the workout detail. |
| F8 | P2 | Canonical Workout Names derived from structure are absent from the domain payload. Frontend titles use generic workout type, so materially different interval prescriptions share one generic title. | Deterministic names distinguish repeat count/work load and survive serialization; LLM wording never owns the canonical name. |
| F9 | P2 | `journeyPhases` in merged `frontend/src/App.vue` always reads `fixturePlanPhases`, with Build marked current, even for authenticated users. The separate API timeline does not correct the main journey. | Authenticated maintenance, race, and no-active-plan states render only canonical Phase Segments, never fixture coaching state. |

The user explicitly requested a visible Recovery Window in the earlier design
decisions. Its background timing exists, but its distinct frontend presentation
is still absent. Treat this as a product acceptance gap even though the written
spec's frontend checklist omitted an explicit component requirement. An empty
schedule or generic health recovery card does not explain the deliberate gap.

## Initial Decisions To Reconcile

- Late background retries intentionally use the later of recovery day eight and
  athlete tomorrow, avoiding dates in the past. Record this existing tested
  exception in the spec when the repair work is reconciled.
- Queued manual work is charged to its queued local `quota_day`. Add a
  cross-midnight contract test and settle whether activation-day or request-day
  attribution is intended before changing quota semantics.
- Far-future race blocks currently include a peak segment. Reconcile their
  actual structure with the agreed base/aerobic-development intent alongside F4.

## Initial Repair Order

1. Protect activation and today's read model (F2, F1), using real persistence
   regressions before claiming failure safety.
2. Make deterministic planning reflect race distance and baseline volume, then
   reconcile repair ordering and executable fallback targets (F4, F6, F7).
3. Correct current-strategy defaults and canonical names (F5, F8).
4. Restore the frontend's complete observation lifecycle and canonical journey;
   expose the Recovery Window (F3, F9, recovery presentation).
5. Rerun affected tests and Stage 7 verification, including component tests once
   dependency startup is reliable. Keep all settled safety constraints intact.

The initial verification-only sweep changed no production code or tests. The
user's subsequent continuation authorized scoped acceptance repairs within
Stage 7; the original findings above are retained as historical evidence.
