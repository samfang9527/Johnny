# Training Plan Regeneration Boundaries and Live LLM Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep regeneration routes free of infrastructure imports, reuse the existing TrainingPlan domain/repository, and validate a real OpenAI result through the production queue and worker.

**Architecture:** Route input/output is translated at the API edge; application query/command handlers load state through ports, call a pure regeneration decision policy and the existing TrainingPlan model, then queue through an injected interface. Production composition selects and persists local or OpenAI provider/model when queueing; worker dispatch honors that immutable choice.

**Tech Stack:** FastAPI, Pydantic, Python dataclasses/Protocols, SQLAlchemy, pytest, PostgreSQL 16, OpenAI Python SDK Responses API.

**Spec:** `docs/superpowers/specs/2026-09-30-training-plan-regeneration-boundaries-and-live-llm.md`; existing plan-generation behavior remains governed by `docs/superpowers/specs/2026-09-17-johnny-training-plan-generation.md` and `docs/adr/0001-deterministic-training-plan-skeletons.md`.

## Global Constraints

- Perform **one stage at a time**; do not begin the next before the current stage is reviewed.
- Do not change HTTP response shape, quota of one successful manual activation per athlete-local day, same-request idempotency, or active-plan supersession timing.
- Preserve existing TrainingPlan and SqlAlchemyTrainingPlanRepository; no second regeneration aggregate/table.
- Route has no infrastructure/SQLAlchemy import; application/domain regeneration modules have no `src.api` or `src.infrastructure` import.
- Key precedence remains `LLM_API_KEY` then `OPENAI_API_KEY`; key plus model selects OpenAI, no key selects local, key without model is an error.
- A queued OpenAI run must never silently execute locally; provider/model are fixed at queue time, and secrets are never persisted/logged.
- Live testing uses synthetic data and disposable PostgreSQL; one paid model sample only after explicit cost/model check, never the developer's existing database.

## File Map

- `backend/src/domain/training_plan.py`: existing saved-plan/workout aggregate; no quota or run fields added.
- `backend/src/domain/training_plan_regeneration.py` (new): pure quota, strategy/admission decision values and functions; no repository imports. Move shared race selection/window calculations here and keep application import compatibility where needed.
- `backend/src/application/training_plan_regeneration.py`: transport-neutral request value, handlers, background orchestration, and calls to the pure policy through injected ports.
- `backend/src/application/interfaces/training_plan_store.py` and narrow regeneration ports: only operations the handlers actually consume.
- `backend/src/api/dependencies.py` or focused `backend/src/api/regeneration_composition.py` (new): concrete request-session composition and user admission lock adapter.
- `backend/src/api/routes/training_plan_regeneration.py`: thin HTTP mapping; no SQL or repository construction.
- `backend/src/infrastructure/llm/settings.py`: key/model-based queued-provider resolver, separate from strict worker configuration.
- `backend/src/api/routes/agent_runs.py`, `scripts/agent_runtime.py`, and worker composition: shared provider selection, pinned dispatch, CLI environment behavior.
- Existing test modules under `backend/tests/unit/` and `backend/tests/integration/`: domain, handler, route, queue, and worker regressions.
- `docs/training_plan_postgresql_verification.md` and `docs/training_plan_live_llm_verification.md`: updated opt-in evidence/runbook steps after behavior exists.

## Review Focus

1. Same `client_request_id` after a failed run and changed provider environment returns the **original** run (Stage A Task 2 and Stage B Task 2).
2. Two simultaneous manual requests for the same athlete admit only one in-flight run under the per-user lock (Stage A Task 2 lock-order test; PostgreSQL verification in Stage C).
3. API has an OpenAI key but worker has none: queued OpenAI run becomes failed, never completed by local fallback (Stage B Task 3).
4. Worker model configuration changes after queueing: execution still uses the model persisted on the run (Stage B Task 3).
5. Invalid/missing model, expired race, or quota exhaustion cannot enqueue a different goal or charge quota (Stage A Task 1 and Stage B Task 1).

---

## Stage A: Route, Handler, and Domain Policy

### Task 1: Pure regeneration decisions and transport-neutral request

**Files:** Create `backend/src/domain/training_plan_regeneration.py`; modify `backend/src/application/training_plan_regeneration.py`; test `backend/tests/unit/test_training_plan_regeneration.py` and new `backend/tests/unit/test_training_plan_regeneration_policy.py`.

**Interfaces:** `RegenerationRequest(client_request_id: str, plan_type: Literal["race", "maintenance"], race_id: str | None)` is an application dataclass. Domain-owned `RegenerationQuota`, `RegenerationStrategy`, and `RegenerationAdmission(action: Literal["reuse", "queue", "unavailable"], existing_run: AgentRun | None)` are immutable values. Pure domain functions are `calculate_regeneration_quota(runs: Sequence[AgentRun], profile: AthleteProfile | None, *, current_instant: datetime, fallback_today: date) -> RegenerationQuota`, `choose_regeneration_strategy(races: Sequence[RaceGoal], *, starts_on: date, explicit_race_id: str | None, force_maintenance: bool) -> RegenerationStrategy`, and `decide_regeneration_admission(runs: Sequence[AgentRun], quota: RegenerationQuota, client_request_id: str) -> RegenerationAdmission`. Move shared race selection/projection-window functions here so domain never imports application; keep compatible application exports for existing generation callers. `TrainingPlan` remains the current-plan input at the handler; no new aggregate is introduced.

- [ ] Write domain tests for priority/date selection, current future race default, explicit maintenance, missing/expired race, athlete-local midnight quota, successful/failed run accounting, same-ID reuse before in-flight reuse, and quota exhaustion. Identify a production change each test would catch.
- [ ] Run `env PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 ./.venv/bin/python -m pytest -q backend/tests/unit/test_training_plan_regeneration_policy.py`; verify the new behavior fails for the expected missing policy interface.
- [ ] Extract only pure decisions from the current application service and shared strategy functions; replace its API-schema request parameter with `RegenerationRequest`. Retain repository orchestration outside the domain module and preserve the existing generation import path while migrating callers.
- [ ] Run both regeneration unit modules; expect all cases pass, including existing background behavior.
- [ ] Commit only this task's files with a focused message.

### Task 2: CQRS handlers, composition, and thin route

**Files:** Modify `backend/src/application/training_plan_regeneration.py`, `backend/src/api/routes/training_plan_regeneration.py`, `backend/src/api/dependencies.py` or new `backend/src/api/regeneration_composition.py`; add a narrow user-lock interface/adapter if needed; test `backend/tests/unit/test_product_workflow_api.py`, `backend/tests/unit/test_training_plan_regeneration.py`, and new `backend/tests/unit/test_regeneration_boundaries.py`.

**Interfaces:** `GetRegenerationOptionsHandler.handle(*, user_id: str, today: date) -> RegenerationOptions`; `StartRegenerationHandler.handle(*, user_id: str, request: RegenerationRequest, today: date) -> RegenerationStartResult`. Inject only the profile/race/plan/run reads, queue interface, and `lock_user(user_id: str) -> None` needed by the command handler. The composition function supplies these from the request session; the route maps Pydantic input to `RegenerationRequest` and maps results to the unchanged response schema. Background scheduling keeps its existing interface, using the shared pure policy where appropriate. Do not move the existing `TrainingPlan` validation or SQL adapter into the new policy.

- [ ] Write a failing import-boundary test using AST/import inspection and handler tests for lock-before-read/queue, same-ID replay, unrelated in-flight reuse, quota exhaustion, and no queue on unavailable race.
- [ ] Run the focused boundary/handler/API tests and verify the intended failures; do not accept a test failing only because a fixture cannot import.
- [ ] Move SQL repository construction and `UserModel` locking to composition/adapters; put query/command orchestration in the two handlers. Do not add a pass-through handler that delegates every operation unchanged to the old service.
- [ ] Run the focused modules, then the full backend suite. Confirm GET/POST payloads and old Active Projection behavior remain unchanged.
- [ ] Commit this task, then obtain a Stage A review before starting Stage B.

## Stage B: Production Provider Choice and Strict Worker Dispatch

### Task 3: Resolve queued provider/model once

**Files:** Modify `backend/src/infrastructure/llm/settings.py`; test `backend/tests/unit/test_llm_settings.py`.

**Interfaces:** `resolve_queued_training_plan_provider() -> tuple[str, str]` returns `("openai", configured_model)` for either configured key plus model; otherwise `("local", "deterministic-local-companion")`. `load_openai_settings_for_queued_model(model: str) -> LlmSettings` requires a runtime key and uses the given persisted model. Unsupported nonempty `LLM_PROVIDER`, key-without-model, and missing worker key for an OpenAI run raise `LlmSettingsError`; empty key with a stale `LLM_PROVIDER=openai` queues local. Neither resolver returns or logs a key except within the in-memory `LlmSettings` used by the gateway.

- [ ] Write failing table-driven tests for both key names and precedence, missing key, whitespace key, missing model, unsupported provider, and provider unset with valid key/model.
- [ ] Run `env PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 ./.venv/bin/python -m pytest -q backend/tests/unit/test_llm_settings.py` and confirm the intended failure.
- [ ] Implement both resolvers without changing synchronous conversation behavior or printing key values.
- [ ] Re-run the module and commit.

### Task 4: Use the resolver at every training-plan queue entry

**Files:** Modify `backend/src/api/regeneration_composition.py` or `backend/src/api/dependencies.py`, `backend/src/api/routes/agent_runs.py`, `scripts/agent_runtime.py`; test `backend/tests/unit/test_product_workflow_api.py`, `backend/tests/integration/application/test_agent_runtime_worker_scheduler.py`, and focused queue-handler tests.

**Interfaces:** One composition helper constructs `QueueAgentRunHandler(..., provider=selected_provider, model=selected_model)` for the UI regeneration path; the raw training-plan endpoint and scheduler call the same resolver. Existing persisted runs keep their original provider/model when idempotency or in-flight rules return them.

- [ ] Write failing tests for UI, raw training-plan endpoint, and scheduled queue metadata under OpenAI/no-key conditions, plus same-ID/in-flight replay across an environment change.
- [ ] Run focused tests and confirm expected metadata failures.
- [ ] Wire the resolver into those three entry points, leaving unrelated conversation/daily-recommendation behavior unchanged.
- [ ] Run focused tests and commit.

### Task 5: Dispatch pinned OpenAI runs or fail visibly

**Files:** Modify `backend/src/api/dependencies.py` and `scripts/agent_runtime.py`; test `backend/tests/unit/test_openai_agent_composition.py`, `backend/tests/integration/application/test_agent_runtime_worker_scheduler.py`.

**Interfaces:** `build_request_companion_agent(session, *, provider: str | None, model: str | None)` keeps existing local behavior; explicit `provider="openai"` calls `load_openai_settings_for_queued_model(model)` and builds the OpenAI gateway with the persisted model, raising a redacted configuration error if unavailable. Unknown explicit providers fail. Worker `work-one`, `work-drain`, and `work-loop` do not erase provider configuration; existing task failure handling records a failed run/task and does not overwrite the previous Active Projection.

- [ ] Write failing tests for queued local under an OpenAI-capable worker, queued OpenAI without worker key, queued OpenAI with a different worker model, provider call failure, and CLI `--database-url`/environment ordering.
- [ ] Run those tests and confirm failures distinguish actual gateway choice, not just run metadata.
- [ ] Implement strict explicit-provider dispatch and remove the CLI provider-clearing behavior for worker/scheduler commands; retain smoke's existing explicit live flag contract or update its tests and help consistently.
- [ ] Run focused tests and the full backend suite; verify no secret appears in persisted metadata or failure messages.
- [ ] Commit and obtain a Stage B review before Stage C.

## Stage C: Integration Evidence

### Task 6: Update opt-in runbooks and deterministic checks

**Files:** Modify `docs/training_plan_live_llm_verification.md` and `docs/training_plan_postgresql_verification.md`; optionally add a narrow integration test under `backend/tests/integration/application/` only where an actual reusable assertion is needed.

**Interfaces:** The live runbook uses only `POST /api/v1/training-plans/regenerations` -> production `work-one`/`work-drain` -> run/steps/plan reads. A patched gateway/composition may remain labeled as diagnostic but is not a PASS path.

- [ ] Update commands for a dedicated `ENV=test` API/worker and isolated database, keeping the local Docker-context and database-identity guards. Require key presence and model validation without printing the key.
- [ ] Add or update deterministic tests for provider routing and persisted completion; run the full backend suite and a syntax check of Bash/Python runbook snippets.
- [ ] Commit documentation/test changes and review the isolation steps before making any paid call.

### Task 7: One authorized PostgreSQL and OpenAI sample

**Files:** No product code; save redacted evidence outside Git in an ignored or temporary directory and summarize results in a verification report if requested.

**Interfaces:** Dedicated disposable PG 16, synthetic athlete, one UI-equivalent product POST, one production worker task, linked run/steps, and saved projection. Record commit, model, run/plan IDs, provider, token usage when returned, structural completeness, and cleanup result. Never put key or raw personal data in artifacts.

- [ ] Confirm the model and acceptable spend with the operator; verify isolated Docker context, database identity, dedicated API/worker environment, key presence, and zero unrelated queued tasks. Stop if any guard fails.
- [ ] Execute the PostgreSQL runbook's existing migration/persistence checks first, then one real product regeneration through the unpatched worker. Do not count a queued or processed task as success.
- [ ] Inspect run status/steps and full saved plan: every planned week, phase segment coverage, Workout Steps/Targets, hard-session safety, and repair/fallback classification. If OpenAI failed or deterministic fallback supplied the plan, report that explicitly.
- [ ] Save redacted evidence, stop API/worker, remove only the dedicated disposable DB/container after identity checks, and report both successes and remaining gaps. Complete Stage C only after verification, not merely because the call returned.
