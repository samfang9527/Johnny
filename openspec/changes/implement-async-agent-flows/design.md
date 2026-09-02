## Context

Johnny already has a `RunningCompanionAgent` that builds workflow-specific `ModelRequest` objects, invokes a model gateway, executes registered tools, persists tool steps, and links created recommendations to agent runs. FastAPI routes can run conversations and recommendation discussion synchronously. The persistence layer stores agent runs, agent run steps, context sources, recommendations, training plans, and workouts.

The missing runtime pieces are asynchronous run creation, a durable local task queue, real worker dispatch, local scheduler behavior, explicit training-plan generation, draft-plan approval, and smoke tests that prove the flow can run automatically on a developer machine.

## Goals / Non-Goals

**Goals:**

- Provide async API-triggered workflows for daily recommendations and training-plan generation.
- Return compact queued responses containing `run_id`, `status`, `workflow_name`, and a relative polling URL.
- Provide user-scoped `GET /api/v1/agent-runs`, `GET /api/v1/agent-runs/{id}`, and `GET /api/v1/agent-runs/{id}/steps`.
- Persist queued runs and queued tasks atomically.
- Use a database-backed local `agent_tasks` queue with AWS-like envelope fields and retry/dead-letter behavior.
- Support local scheduler and worker one-shot, drain, and loop modes from one CLI script and Make targets.
- Keep daily scheduling to today's jobs only for active users with athlete profile and active training plan.
- Add explicit training-plan generation that can produce race plans or base plans.
- Store generated plans as draft training plans and create pending user-approval recommendations.
- Activate draft plans only after recommendation acceptance, superseding conflicting active plans.
- Use deterministic local gateway behavior for local smoke tests and opt-in live OpenAI smoke for configurable workflows.

**Non-Goals:**

- No production AWS EventBridge/SQS/Lambda implementation in this change.
- No LocalStack requirement.
- No public task queue inspection API.
- No cancellation API.
- No frontend implementation.
- No direct LLM application of significant training-plan changes.
- No backfilling missed daily recommendations.

## Decisions

### Add Async Product Endpoints Instead Of A Generic Workflow Endpoint

Add dedicated endpoints for product workflows:

- `POST /api/v1/agent-runs/daily-recommendation`
- `POST /api/v1/agent-runs/training-plan-generation`

The existing `POST /api/v1/conversations/messages` remains synchronous for current UX. A generic `workflow_name` endpoint is avoided so clients cannot invoke arbitrary internal workflows.

Daily recommendation accepts optional `anchor_date` and `force`. Training-plan generation accepts optional `race_id`, `starts_on`, `ends_on`, `plan_horizon_weeks`, `goal_notes`, and `plan_type` with values such as `race` and `base`.

### Create Queued Run And Task Atomically

Async trigger handlers create an `AgentRun` with status `queued` and an `agent_tasks` row in one transaction. The task payload references the run id and trusted workflow input. The response contains the queued run id, status, workflow name, and relative polling URL.

`AgentRun.started_at` should represent worker execution start time. Enqueue time is represented by the database row timestamps. Polling APIs expose run timestamps and status without exposing task internals.

### Use A Database-Backed Local Agent Task Queue

Add `agent_tasks` with fields sufficient for local reliability and future SQS mapping:

- id
- task_type
- status: `queued`, `processing`, `completed`, `failed`, `dead_lettered`
- correlation_id
- idempotency_key
- payload JSON
- available_at
- claimed_at
- completed_at
- failed_at
- retry_count
- max_attempts
- last_error_type
- last_error_message
- created_at / updated_at

The queue claims the oldest available task ordered by `available_at`, then `created_at`. Processing tasks may be reclaimed after a configurable claim timeout, defaulting to 5 minutes. Duplicate scheduled daily tasks are prevented by idempotency key `daily_recommendation:{user_id}:{anchor_date}` unless `force=true`, which creates a distinct idempotency key and does not mutate history.

### Retry Only Retryable Failures

Tasks retry up to 3 times, but do not retry domain validation errors, safety blocks, unknown workflow/task type, or malformed payload errors. Exhausted retryable failures become `dead_lettered`, store retry count, last error type/message, failed timestamp, and mark the linked run failed. Full tracebacks should not be persisted.

### Implement Local Scheduler And Worker CLI

Create one script, for example `scripts/agent_runtime.py`, with subcommands:

- `schedule-once`
- `schedule-loop`
- `work-one`
- `work-drain`
- `work-loop`
- `smoke`

Scheduler loop supports `--max-iterations`, defaulting to forever. Worker loop supports `--idle-timeout-seconds`. Smoke waits for queued runs with configurable timeout defaulting to 30 seconds, exercises HTTP API endpoints where appropriate, and keeps direct application tests for precise failure coverage.

Makefile targets should cover scheduler and worker one-shot/drain/loop commands plus deterministic and opt-in OpenAI smoke workflows.

### Add Training Plan Draft Lifecycle

Extend valid training plan statuses with `draft` and `superseded`. Manual plan creation may continue to create `active` plans. Generated training-plan workflow stores output as a draft plan.

For race plans, the workflow uses an explicit `race_id` when provided; otherwise it selects the earliest future primary race, then the earliest future race. For no-race users, `plan_type=base` can generate an 8-week base plan. Race-plan defaults start on the creation date and run through race date, capped at 16 weeks unless the request supplies a shorter date range or horizon.

### Add Training Plan Creation Recommendations

Extend recommendation types with `training_plan_creation` and proposed action support with:

```json
{
  "type": "create_training_plan",
  "draft_training_plan_id": "...",
  "reason": "...",
  "summary": "..."
}
```

The recommendation is the user-facing approval object. `AgentRun.recommendation_id` links to this recommendation. The draft training plan id lives in the proposed action payload.

On acceptance, the handler verifies ownership, verifies the draft is still draft, rejects expired race drafts after race date, and blocks acceptance if a newer active plan for the same race was created after the recommendation. If accepted, the draft becomes active. Existing active plans for the same race are superseded; for base plans without race, active plans with overlapping dates are superseded.

### Add A Draft Plan Tool And Validation Repair Loop

Add `createDraftTrainingPlan` as a write tool. `training_plan_generation` allows read tools plus `createDraftTrainingPlan` and `createRecommendation`.

The LLM may propose structured workouts, but the server validates dates, workout types, duration/distance, plan range, ownership, and safe lifecycle states before storage. If the LLM proposes an invalid draft plan, the runtime asks the model to repair once using the original request and validation errors, without echoing the full invalid JSON payload. If repair fails, the run fails with inspectable step details.

Malformed tool arguments in training-plan generation follow the repair path. Other workflows fail malformed tool calls as non-retryable workflow errors.

### Preserve Local And Live LLM Boundaries

Default local automation uses deterministic local model behavior. The local gateway should create a realistic 4-week draft plan with 3-5 workouts per week for training-plan generation and a pending recommendation so the approval loop can be tested without OpenAI.

Live OpenAI smoke remains opt-in and configurable by workflow, with conversation as the default.

## Risks / Trade-offs

- Database-backed local queue is not identical to SQS, but the AWS-like envelope and retry/dead-letter semantics reduce migration risk without requiring LocalStack.
- Draft plan activation can conflict with newer plans; blocking stale acceptance protects user intent at the cost of requiring regeneration.
- Extending recommendation and plan status constraints requires a migration and careful SQLite/PostgreSQL test coverage.
- LLM-generated plan structure can be malformed; server validation plus one repair attempt avoids silent bad drafts while keeping failures debuggable.
- Scheduling every context-ready user can create unnecessary work if demo/test data is broad; limiting daily jobs to active users with profiles and active plans controls that risk.

## Migration Plan

1. Add the `agent_tasks` table and status constraints.
2. Allow `queued` agent runs.
3. Allow `draft` and `superseded` training plan statuses.
4. Allow `training_plan_creation` recommendation type and `create_training_plan` proposed action payloads.
5. Add repository/application methods for queued runs, task publishing/claiming/completion/failure, draft plan creation, and draft activation.
6. Add async API routes and schemas.
7. Add worker/scheduler/CLI behavior.
8. Add deterministic and optional live smoke coverage.

Rollback is to stop using the new async endpoints and local scheduler/worker. Historical queued/failed/completed run and task records can remain in the database; application code should ignore unknown or inactive tasks after rollback.

## Resolved Product Decisions

- Race-plan generation uses a maximum 16-week horizon from the creation date through the selected race date.
- A later frontend change should provide a modal for draft-plan review before approval.
