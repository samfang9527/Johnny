## 1. OpenSpec Approval

- [ ] 1.1 Review `feature.md`, `proposal.md`, spec deltas, and `design.md` with the product owner.
- [ ] 1.2 Receive explicit product-owner approval for `design.md` before implementation starts.

## 2. Persistence And Domain Lifecycle

- [ ] 2.1 Add one Alembic migration for `agent_tasks`, queued run status, draft/superseded plan status, and training-plan-creation recommendation support.
- [ ] 2.2 Update SQLAlchemy models and domain constants for queued runs, draft/superseded plans, and training-plan creation recommendations.
- [ ] 2.3 Add SQLite-compatible and optional PostgreSQL migration/schema tests for the new table, constraints, and metadata.
- [ ] 2.4 Add repository behavior for creating queued runs, listing runs, loading steps, creating draft plans, activating drafts, and superseding conflicting plans.

## 3. Local Task Queue

- [ ] 3.1 Add a database-backed agent task queue interface and SQLAlchemy implementation.
- [ ] 3.2 Implement atomic queued-run/task creation with idempotency keys and AWS-like envelopes.
- [ ] 3.3 Implement task claiming ordered by `available_at`, then `created_at`, with configurable claim timeout.
- [ ] 3.4 Implement completion, retry, non-retryable failure, and dead-letter transitions.
- [ ] 3.5 Add unit/integration tests for idempotency, claiming, retry, dead-letter, malformed payload, and unknown task behavior.

## 4. Agent Workflows

- [ ] 4.1 Add `training_plan_generation` orchestration to `RunningCompanionAgent`.
- [ ] 4.2 Add `createDraftTrainingPlan` tool and allow it only in training-plan generation.
- [ ] 4.3 Add race selection for explicit race, earliest future primary race, earliest future race, and explicit base-plan generation.
- [ ] 4.4 Add validation repair once for invalid training-plan generation output.
- [ ] 4.5 Extend deterministic local gateway to generate a valid 4-week draft plan and pending recommendation.
- [ ] 4.6 Add tests for daily recommendation, conversation preservation, training-plan generation, repair behavior, and non-retryable validation/safety failures.

## 5. Recommendation Approval

- [ ] 5.1 Add `create_training_plan` proposed action validation.
- [ ] 5.2 Add acceptance behavior for draft plan activation, race-date expiration rejection, stale newer-active-plan conflict, and superseding conflicting active plans.
- [ ] 5.3 Add rejection/edit behavior coverage for training-plan creation recommendations.
- [ ] 5.4 Add API/repository tests proving another user cannot approve or inspect draft plan recommendations.

## 6. Async API

- [ ] 6.1 Add async trigger schemas and compact queued response schema.
- [ ] 6.2 Add `POST /api/v1/agent-runs/daily-recommendation` with optional `anchor_date` and `force`.
- [ ] 6.3 Add `POST /api/v1/agent-runs/training-plan-generation` with optional race, date, horizon, plan type, and notes inputs.
- [ ] 6.4 Add user-scoped `GET /api/v1/agent-runs`, `GET /api/v1/agent-runs/{id}`, and `GET /api/v1/agent-runs/{id}/steps`.
- [ ] 6.5 Keep `POST /api/v1/conversations/messages` synchronous for current UX.
- [ ] 6.6 Add API tests for queued responses, polling, run filtering, step retrieval, authorization, and idempotency.

## 7. Scheduler, Worker, And Smoke

- [ ] 7.1 Implement `scripts/agent_runtime.py` with `schedule-once`, `schedule-loop`, `work-one`, `work-drain`, `work-loop`, and `smoke`.
- [ ] 7.2 Add scheduler eligibility for active users with athlete profile and active training plan, emitting only today's daily jobs.
- [ ] 7.3 Add worker dispatch for agent task types and linked run status transitions.
- [ ] 7.4 Add loop controls for scheduler max iterations and worker idle timeout.
- [ ] 7.5 Add Makefile targets for scheduler, worker, deterministic smoke, and configurable live OpenAI smoke.
- [ ] 7.6 Add smoke tests that exercise HTTP API triggers, drain local work, poll run completion, and verify created recommendations/draft plans.

## 8. Documentation And Verification

- [ ] 8.1 Update `README.md` with async local agent setup, CLI commands, Make targets, and OpenAI smoke configuration.
- [ ] 8.2 Update `docs/manual_test_runbook.md` with end-to-end local API/worker/scheduler flow.
- [ ] 8.3 Add architecture documentation for async agent runtime, local DB queue, and future AWS mapping.
- [ ] 8.4 Run focused backend tests for persistence, queue, workflows, API, worker/scheduler, and smoke helpers.
- [ ] 8.5 Run the full backend test suite.
