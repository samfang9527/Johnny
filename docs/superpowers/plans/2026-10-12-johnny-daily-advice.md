# Johnny Daily Advice Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publish one current, evidence-backed Daily Advice per athlete-local day after activity sync, with a plan-week review and guidance that never changes the planned workout.

**Architecture:** A deterministic policy resolves the Plan Version's seven-day week and compares planned workouts with local-dated activities. A separate Daily Advice workflow syncs first, generates constrained Traditional Chinese coaching from those facts, and atomically replaces the current date's read model. Approval-backed Recommendations remain a separate write path.

**Tech Stack:** Python 3, FastAPI/Pydantic, SQLAlchemy/Alembic, pytest, existing agent task queue and Garmin adapter, Vue 3/TypeScript, Vitest.

**Spec:** [GitHub issue #13](https://github.com/samfang9527/Johnny/issues/13). Read its acceptance scenarios and the repo's CONTEXT.md, UX-CONTRACT.md, and docs/adr/0001-deterministic-training-plan-skeletons.md before implementing.

## Global Constraints

- "This week" is the owning Plan Version's seven-day block from its starts_on date, ending at six days or its ends_on date.
- Scheduled advice is due at or after 04:00 in the athlete profile timezone; one scheduled run per athlete-local date, including DST/restart catch-up before local midnight.
- Sync active Garmin activities before scheduled generation. A successful manual sync queues another generation; activity sync failure or reauth never publishes fresh-looking advice.
- Exactly one current Daily Advice per athlete-local date is visible. Keep previous content on failed refresh; a later input snapshot wins over an older run that finishes late.
- Advice state (pending, ready, sync_failed, generation_failed, no_plan) and data freshness (fresh, limited, stale) are separate; a failed refresh can retain ready content marked stale.
- Daily Advice has three Traditional Chinese sections: plan-week execution summary, today's execution advice, and workout guide. No plan/workout/adjustment mutation and no Approve/Reject actions.
- Keep approval-backed Recommendations and their accept/reject/edit contracts for genuine proposed plan changes. Daily Advice never automatically creates one.
- Use the spec's initial 25% plus 30-minute over/under thresholds and missed-session rule in deterministic code, not a prompt.
- Production queueing uses the configured model provider; local/test mode produces all three sections deterministically. Normal tests make no live Garmin or OpenAI calls.
- When implementing the UI task, use frontend-design and frontend-design-premium together and preserve DESIGN.md and UX-CONTRACT.md.

## File Map

- backend/src/application/daily_advice_context.py: owner Plan Version, local dates, widened UTC activity query, and deterministic plan-week facts.
- backend/src/domain/daily_advice.py: WeekExecution, AdviceSections, RefreshVersion, and DailyAdvice value objects; no approval behavior.
- backend/src/infrastructure/database/daily_advice_repository.py and backend/migrations/versions/0011_add_daily_advice.py: one current row per athlete/date, guarded refresh/publish, and provenance.
- backend/src/application/daily_advice_generation.py: constrained model request, output validation, safe local text, AgentRun completion; no Recommendation tool.
- backend/src/application/daily_advice_sync.py: resource-level sync gate and sync-to-generation handoff.
- scripts/agent_runtime.py and backend/src/application/async_agent_runs.py: local-time scheduler, sync task, worker dispatch, idempotency, and provider choice.
- backend/src/api/routes/today.py, backend/src/api/routes/agent_runs.py, backend/src/api/routes/integrations.py and schemas: date-scoped read and refresh status.
- frontend/src/components/DailyAdviceCard.vue, frontend/src/types.ts, frontend/src/api/client.ts, and frontend/src/App.vue: one current advice, truthful loading/freshness states, and sync refresh.
- CONTEXT.md, UX-CONTRACT.md, README.md, and affected openspec/specs files: align language and operational contract.

## Review Focus

1. A run just after UTC midnight belongs to the athlete's previous local date; local activity filtering and schedule keys remain correct (Tasks 1 and 5).
2. Two workouts or two unmatched runs on one day never create a confident completion or missed claim (Task 1).
3. A Garmin activities resource with zero fetched records is still a successful fresh sync, while a failed/omitted activities resource is not (Task 4).
4. A scheduled run finishing after a newer manual sync cannot replace the newer snapshot, even if the newer generation fails (Tasks 2 and 8).
5. A Plan Version switch, rest day, race without prescribed minutes, or absent owning plan does not invent volume or a workout (Tasks 1, 3, and 6).

---

### Task 1: Deterministic plan-week facts

**Files:** Create backend/src/domain/daily_advice.py and backend/src/application/daily_advice_context.py; modify backend/src/application/training_analytics.py only to share its plan-for-date resolution; test backend/tests/unit/test_daily_advice_context.py and backend/tests/unit/test_daily_advice_policy.py.

**Interfaces:** resolve_plan_for_date(plans: TrainingPlanStore, user_id: str, anchor_date: date) -> TrainingPlan | None; plan_week_for_date(plan: TrainingPlan, anchor_date: date) -> tuple[date, date]; build_week_execution(plan: TrainingPlan, activities: tuple[CompletedActivity, ...], *, anchor_date: date, as_of: datetime, timezone_name: str, activity_coverage_complete: bool) -> WeekExecution. WeekExecution exposes status (`on_plan`, `above`, `behind`, `mixed`, `insufficient_evidence`), week dates, completed/missed/extra counts, comparable planned/actual minutes, available distance, today's completion flag, and evidence through to_payload(). An absent comparable minute denominator yields insufficient evidence unless the count-based two-missed-session rule independently supports behind.

- [ ] Write failing tests for non-Monday plan starts, plan switch, local dates crossing UTC, future/today not missed, explicit match precedence, one-to-one same-day fallback, ambiguous matches, extra/non-running activity, race-only duration, rest day, and each exact threshold/status including mixed and insufficient evidence. Pin boundaries: above requires >25% and >=30 excess minutes; behind requires two certain misses, or one certain miss plus >=25% and >=30 deficit minutes.
- [ ] Run: env PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest -q backend/tests/unit/test_daily_advice_context.py backend/tests/unit/test_daily_advice_policy.py. Expect failures for the new interfaces.
- [ ] Implement the pure policy and a context loader that queries an extra UTC day on each edge before filtering timestamps in ZoneInfo(profile.timezone). Share the existing predecessor-plan resolution rather than copying it. Compare only elapsed workouts; do not infer a miss when coverage or attribution is uncertain.
- [ ] Re-run the two modules; expect all new cases to pass.
- [ ] Commit with feat: derive plan-week execution facts.

### Task 2: One current advice with guarded replacement

**Files:** Create backend/src/infrastructure/database/daily_advice_repository.py and backend/migrations/versions/0011_add_daily_advice.py; modify backend/src/infrastructure/database/models.py; test backend/tests/integration/database/test_daily_advice_repository.py and backend/tests/integration/database/test_alembic_migrations.py.

**Interfaces:** RefreshVersion(observed_at: datetime, run_id: str) orders input snapshots; observed_at is the activity sync's start time, or the queue time when no provider is connected. DailyAdvice carries user_id, advice_date, plan_version_id, optional workout_id, week_start/end, execution_mode, WeekExecution facts, AdviceSections, generated_at, source_sync_run_id, source_run_id, state, and data_freshness. SqlAlchemyDailyAdviceRepository has get_for_user_date(user_id: str, advice_date: date) -> DailyAdvice | None, begin_refresh(user_id: str, advice_date: date, version: RefreshVersion, source_sync_run_id: str | None) -> bool, publish(user_id: str, advice_date: date, version: RefreshVersion, advice: DailyAdvice) -> bool, and mark_failed(user_id: str, advice_date: date, version: RefreshVersion, state: str) -> bool. begin_refresh creates a placeholder or marks an existing row pending without erasing content. publish/mark_failed only affect the reserved version.

- [ ] Write failing repository/migration tests for unique (user_id, advice_date), owner isolation, absent-content failure row, previous-content preservation, newer reservation rejecting older publish even after the newer generation fails, repeated same-run idempotency, and persistence of plan/workout IDs, sections, facts, generated_at, source sync/run IDs.
- [ ] Run: env PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest -q backend/tests/integration/database/test_daily_advice_repository.py backend/tests/integration/database/test_alembic_migrations.py. Expect table/repository failures.
- [ ] Add the model and migration with a revision ID under 32 characters. Use a database conditional update or row lock plus unique constraint for version comparison; do not implement read-then-unconditional-write. States are pending, ready, sync_failed, generation_failed, and no_plan; failure retains prior sections and generation time.
- [ ] Re-run the two modules; expect SQLite migration and guarded update tests to pass.
- [ ] Commit with feat: persist one current daily advice per date.

### Task 3: Generate three sections without creating a Recommendation

**Files:** Create backend/src/application/daily_advice_generation.py; modify backend/src/infrastructure/llm/openai_gateway.py, backend/src/infrastructure/llm/local_gateway.py, backend/src/infrastructure/llm/settings.py, backend/src/application/agent_runtime.py, and scripts/agent_runtime.py; test backend/tests/unit/test_daily_advice_generation.py, backend/tests/unit/test_openai_agent_composition.py, and backend/tests/integration/application/test_agent_runtime_worker_scheduler.py.

**Interfaces:** Define DailyAdviceModelGateway(Protocol) with complete(request: ModelRequest) -> ModelResponse. DailyAdviceGenerator.generate(*, user_id: str, facts: WeekExecution, workout: Workout | None, recovery: dict, gateway: DailyAdviceModelGateway) -> AdviceSections. ModelRequest for daily_recommendation allows only composeDailyAdvice, whose arguments are week_summary, today_execution, and workout_guide with purpose, expected_feel, if_too_hard, if_too_easy. GenerateDailyAdviceHandler.handle(*, user_id: str, anchor_date: date, run: AgentRun, version: RefreshVersion, source_sync_run_id: str | None) -> AgentRun. DailyAdvice.execution_mode is deterministic: completed when today's activity is evidenced, rest on a rest day or rest-level recovery, ease_off for behind/above/mixed or caution-level recovery, and follow_plan otherwise; insufficient evidence receives conservative follow_plan wording without a strong adherence claim. The completed run records daily_advice_id in metadata; recommendation_id stays null.

- [ ] Write failing tests for valid Traditional Chinese sections, on-plan/over/behind/rest/already-completed local output, sparse-data uncertainty, rejected empty/malformed tool output, configured OpenAI provider selection, and no createRecommendation/proposeWorkoutAdjustment call or plan mutation.
- [ ] Run: env PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest -q backend/tests/unit/test_daily_advice_generation.py backend/tests/unit/test_openai_agent_composition.py backend/tests/integration/application/test_agent_runtime_worker_scheduler.py. Expect daily output assertions to fail.
- [ ] Implement a constrained composeDailyAdvice schema and validation against trusted facts. The application, not the model, owns status, counts, mode, and target evidence; local mode uses deterministic text, while invalid configured-model output fails the refresh and preserves prior advice. Route worker daily_recommendation dispatch to this handler and remove the old daily entry point that creates a pending Recommendation. Preserve agent-run steps, token usage, and failure reporting.
- [ ] Re-run the three modules; expect daily runs to create Daily Advice only, while conversation and plan-generation regressions remain green.
- [ ] Commit with feat: generate structured daily advice.

### Task 4: Sync gate and manual-sync refresh

**Files:** Create backend/src/application/daily_advice_sync.py; modify backend/src/application/async_agent_runs.py, backend/src/api/routes/integrations.py, backend/src/api/schemas/integrations.py, and scripts/agent_runtime.py; test backend/tests/unit/test_daily_advice_sync.py, backend/tests/integration/application/test_agent_runtime_worker_scheduler.py, and backend/tests/unit/test_garmin_initial_sync_application.py.

**Interfaces:** activity_sync_usable(summary: SyncSummary, sync_status: str, credential_status: str) -> bool requires an attempted successful activities resource, including fetched=0. QueueAgentRunHandler.queue_run gains task_type: str = "agent.workflow". Scheduled runs start as daily_advice.sync tasks linked to an AgentRun; successful sync enqueues one agent.workflow generation task for that same run. IntegrationConnectionResponse gains optional daily_advice_run containing run_id, status, workflow_name, poll_url.

- [ ] Write failing tests proving scheduled sync precedes the generation task's database read, explicit sync/connect/token-import queues once by sync_run_id after committed import, activities failure/reauth blocks generation, health-only failure permits a flagged limited-recovery run, no connection uses stored data with limited coverage, no owning plan does not invent advice, and a concurrent existing sync defers rather than reads stale data.
- [ ] Run: env PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest -q backend/tests/unit/test_daily_advice_sync.py backend/tests/integration/application/test_agent_runtime_worker_scheduler.py backend/tests/unit/test_garmin_initial_sync_application.py. Expect ordering and enqueue failures.
- [ ] Implement the sync gate using the existing Garmin handler, resource summaries, and backoff metadata. In the worker, complete sync plus enqueue generation in one committed transaction before any worker can claim generation, including work_drain. Mark failed refresh without deleting previous content; never start a second Garmin sync when one is running. Queue manual refresh in the same API transaction as the successful sync so both become visible together after commit, not only in Vue.
- [ ] Re-run the three modules; expect sync ordering, partial-failure, and idempotency cases to pass.
- [ ] Commit with feat: refresh advice after committed activity sync.

### Task 5: Athlete-local 04:00 scheduling and runtime operation

**Files:** Modify scripts/agent_runtime.py, backend/src/infrastructure/llm/settings.py, README.md, and Makefile only where the runtime command contract changes; test backend/tests/integration/application/test_agent_runtime_worker_scheduler.py and backend/tests/unit/test_daily_advice_schedule.py.

**Interfaces:** schedule_once(session: Session, *, now: datetime | None = None) -> int uses timezone-aware UTC now, converts it per profile, and queues one daily_advice.sync task for each user with an owning Plan Version whose local clock is at least 04:00. The idempotency key contains user ID and athlete-local date. Reuse the same provider resolver policy as configured training-plan runs.

- [ ] Write failing fake-clock tests for 03:59/04:00, users in different timezones at one instant, spring/fall DST days, scheduler restart at 23:59, repeat ticks, timezone change, no owning plan, and model-provider metadata. Assert one task per user and local date, with none before 04:00. Keep the training-plan daily-check task's existing behavior.
- [ ] Run: env PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest -q backend/tests/unit/test_daily_advice_schedule.py backend/tests/integration/application/test_agent_runtime_worker_scheduler.py. Expect current server-date scheduling to fail.
- [ ] Implement due-user selection and durable per-local-date keys. Document that the existing schedule-loop and work-loop processes must run continuously for unattended advice, including startup/catch-up and health monitoring; the repository's Terraform template currently provisions only the API service, so document a production rollout requirement for separately supervised scheduler and worker processes.
- [ ] Re-run the two modules and a local schedule-once/work-drain smoke using fake provider data; expect one advice per eligible local date.
- [ ] Commit with feat: schedule advice at athlete-local 4am.

### Task 6: Date-scoped API and run status

**Files:** Modify backend/src/api/routes/today.py, backend/src/api/schemas/today.py, backend/src/api/routes/agent_runs.py, backend/src/api/schemas/agent_runs.py, and backend/src/api/dependencies.py; create backend/tests/unit/test_daily_advice_api.py and extend backend/tests/integration/application/test_agent_runtime_worker_scheduler.py.

**Interfaces:** GET /api/v1/today?anchor_date=YYYY-MM-DD adds daily_advice with state, generated_at, source freshness, execution_mode, plan week, structured facts, and all three sections or null content. AgentRunResponse adds daily_advice_id, read from run metadata; recommendation_id remains null for advice. POST /api/v1/agent-runs/daily-recommendation retains run_id/status/workflow_name/poll_url and force behavior but follows the sync-first path.

- [ ] Write failing API tests for owner isolation, requested-date isolation, pending/ready/sync_failed/generation_failed/no_plan states, independent fresh/limited/stale freshness, stable prior content after failure, forced rerun yielding one current advice, and coexistence with a separately pending approval Recommendation.
- [ ] Run: env PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest -q backend/tests/unit/test_daily_advice_api.py backend/tests/integration/application/test_agent_runtime_worker_scheduler.py. Expect missing fields or old pending-recommendation behavior.
- [ ] Add the Today read field and run response mapping. Reuse the existing authenticated Today route rather than a second read endpoint. Keep GET /recommendations and accept/reject/edit endpoints unchanged.
- [ ] Re-run the two modules; expect date/owner and contract cases to pass.
- [ ] Commit with feat: expose current daily advice on Today.

### Task 7: Show one current advice on Today and Johnny

**Files:** Create frontend/src/components/DailyAdviceCard.vue; modify frontend/src/types.ts, frontend/src/api/client.ts, frontend/src/App.vue, and frontend/src/styles.css; test frontend/src/App.test.ts and create frontend/src/components/DailyAdviceCard.test.ts.

**Interfaces:** Today response maps daily_advice to a typed DailyAdvice with state, generatedAt, planWeek, facts, weekSummary, todayExecution, and workoutGuide. DailyAdviceCard receives this object and emits no approval action. Manual Garmin sync may return daily_advice_run; poll its existing agent-run URL and refresh Today once completed. Today Decision derives any Run/Adjust/Rest wording from the validated advice mode when ready, with a non-contradictory fallback while pending/stale.

- [ ] Write failing component tests for all three Traditional Chinese sections, one card after manual replacement, no Approve/Reject actions on advice, separate pending Recommendation actions, rest/already-completed states, stale time/warning, generation failure, no plan, no connected source, narrow viewport, and a sync refresh completing while Today is open.
- [ ] Run: cd frontend && npm test -- App.test.ts DailyAdviceCard.test.ts. Expect missing advice component/state assertions.
- [ ] Implement the card and state mapping. Keep the planned workout card unchanged. Show only a concise Today entry point if Johnny carries the full sections, but make all sections reachable from Today; never render two revisions together. Use focus/visibility or the existing minute tick to refresh a long-open app after 04:00 without unbounded polling.
- [ ] Re-run focused tests, then cd frontend && npm run build and cd frontend && npm run verify:tokens; expect all pass.
- [ ] Commit with feat: show one daily advice without approval actions.

### Task 8: Cross-path proof and contract alignment

**Files:** Create backend/tests/integration/application/test_daily_advice_flow.py; modify openspec/specs/backend-api/spec.md, openspec/specs/recommendation-approval/spec.md, affected Today/Johnny frontend specs, CONTEXT.md, UX-CONTRACT.md, and README.md. Update DESIGN.md only if UI behavior needs new durable visual guidance.

**Interfaces:** Exercise schedule -> Garmin fake sync -> committed activity -> deterministic facts -> local model -> one persisted advice -> Today API, then manual sync -> replacement. Read both issue #13 and the existing approval specs when editing; remove only the outdated assertion that daily advice is pending.

- [ ] Write the end-to-end test with a synthetic athlete and fake Garmin adapter: an over-plan week at 04:00, a later manual sync changing facts, prior content surviving failed sync, an older run losing the guarded publish race, and a separate pending workout-adjustment Recommendation still requiring approval.
- [ ] Run: env PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest -q backend/tests/integration/application/test_daily_advice_flow.py. Expect any remaining seam to fail before final fixes.
- [ ] Align specs/domain/UX text with Daily Advice as read-only and Recommendation as approval-backed. Rewrite the old daily-recommendation creation and service-shell scenarios so they apply only to separate plan-change proposals. Explain the 04:00 scheduler and worker process contract, provider configuration, no-connection behavior, and failure freshness state in README.
- [ ] Run: env PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest -q backend/tests; cd frontend && npm test; cd frontend && npm run build; cd frontend && npm run verify:tokens; git diff --check. Record actual results and any environment-only skip.
- [ ] Commit with feat: verify daily advice across sync and UI.
