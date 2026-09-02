# Agent Runtime Tools

This document describes the MVP Running Companion Agent implementation. The agent is an application-layer orchestrator that reaches project data only through explicit tools, records every run through existing observability tables, and creates proposals instead of applying training changes directly.

```mermaid
flowchart TD
    Trigger["Scheduled or manual trigger"] --> Agent["RunningCompanionAgent"]
    Agent --> RunStore["AgentRunStore"]
    Agent --> Gateway["ModelGateway"]
    Agent --> Registry["AgentToolRegistry"]
    Registry --> ReadTools["Read tools: athlete, plan, workout, activities, recovery, metrics"]
    Registry --> WriteTools["Write tools: recommendations, workout adjustment proposals, memory candidates, draft plans"]
    ReadTools --> Stores["Application stores/providers"]
    Stores --> Domain["Deterministic domain/application services"]
    WriteTools --> Approval["Recommendation approval boundary"]
    RunStore --> Observability["agent_runs, agent_run_steps, agent_context_sources"]
    Approval --> Pending["Pending user approval"]
```

## Boundaries

- `RunningCompanionAgent` coordinates prompts, model calls, tool execution, safety checks, and observability.
- `ModelGateway` isolates provider-specific LLM calls. Tests use `FakeModelGateway` and do not require network access.
- `AgentRunStore` records top-level runs, ordered steps, and context sources.
- Read tools return structured payloads and filter by trusted `user_id`.
- Write tools create pending recommendations, workout adjustment proposals, memory candidates, or generated draft plans. They do not directly activate or supersede training plans.

## Async Runtime

Johnny supports local async execution for product workflows that should not block the current UI request:

- `POST /api/v1/agent-runs/daily-recommendation`
- `POST /api/v1/agent-runs/training-plan-generation`

Each trigger creates an `agent_runs` row with status `queued` and an `agent_tasks` row in the same database transaction. The API returns a compact response with `run_id`, `status`, `workflow_name`, and `poll_url`.

The local queue table is intentionally shaped like a future SQS envelope:

- `task_type`
- `correlation_id`
- `idempotency_key`
- `payload`
- `available_at`
- claim/completion/failure timestamps
- retry count, max attempts, and safe error summary fields

Workers claim the oldest available task by `available_at`, then `created_at`. A stale `processing` task can be reclaimed after the configured claim timeout. Retryable failures can be requeued with delay until attempts are exhausted; non-retryable validation, malformed payload, unknown workflow, and unknown task failures are marked failed without storing tracebacks.

## Scheduler And Worker

The local runtime entry point is `scripts/agent_runtime.py`:

```bash
PYTHONPATH=backend ./.venv/bin/python scripts/agent_runtime.py schedule-once
PYTHONPATH=backend ./.venv/bin/python scripts/agent_runtime.py work-drain
```

Make targets wrap the common commands:

- `make agent-schedule-once`
- `make agent-schedule-loop`
- `make agent-work-one`
- `make agent-work-drain`
- `make agent-work-loop`
- `make smoke-agent-local`
- `make smoke-agent-openai`

The scheduler only emits today's daily recommendation jobs for active users with both an athlete profile and an active training plan. It does not backfill missed days.

## Generated Training Plans

The `training_plan_generation` workflow selects an explicit race when supplied, otherwise the earliest future primary race, otherwise the earliest future race. `plan_type=base` creates a no-race base-plan draft.

The model may call `createDraftTrainingPlan` and `createRecommendation` in this workflow. `createDraftTrainingPlan` stores a `draft` plan only. The generated `training_plan_creation` recommendation references that draft through a `create_training_plan` proposed action. Accepting the recommendation activates the draft and supersedes conflicting active plans; rejecting it leaves the draft inactive.

If the model proposes an invalid draft plan, the agent asks for one repair using validation errors. A second invalid response fails the run with inspectable step details.

## Future AWS Mapping

The local scheduler maps to EventBridge or EventBridge Scheduler. `agent_tasks` maps to SQS message envelopes, including idempotency and correlation fields. The worker command maps to a Lambda-style task handler. The current local database queue keeps MVP development deterministic while preserving the production direction.

## Safety

Pain, injury-adjacent, illness, and medical-style prompts are classified before tool execution. In conservative mode, aggressive workout increases are blocked before persistence and the output summary includes non-diagnostic guidance to reduce or stop training when appropriate and consult a medical professional for severe, persistent, or unusual symptoms.
