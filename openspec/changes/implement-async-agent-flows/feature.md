# Async Agent Flows

## Product Summary

Johnny needs an end-to-end agent runtime that can be called through product APIs, execute LLM-backed workflows through background work, and run locally with enough fidelity to prove the later AWS EventBridge/SQS/Lambda deployment shape.

The MVP completion bar is:

- API callers can trigger explicit product workflows for daily recommendations and training-plan generation.
- Conversation remains synchronous for current UX, while heavier or scheduled workflows use async runs.
- Local development can run the full stack with database persistence, scheduler commands, worker commands, deterministic model behavior, and smoke tests.
- Live OpenAI checks remain opt-in and configurable.

## Workflows

### `coach_conversation`

Conversation remains available through `POST /api/v1/conversations/messages` and continues to produce a conversation-visible response or run reference. This workflow may create pending recommendations but should preserve immediate UX behavior for now.

### `daily_recommendation`

Daily recommendation becomes an async product workflow. The API creates a queued agent run and a database-backed task atomically, returns a compact queued response, and lets the worker execute the existing Running Companion Agent workflow.

Default `anchor_date` is derived from the athlete profile timezone, with UTC fallback. Manual requests can provide `anchor_date` and `force=true` to create a distinct rerun with a unique idempotency key.

Scheduled local daily jobs are eligible for active users with an athlete profile and an active training plan. The scheduler emits only today's jobs for MVP and does not backfill missed days.

### `training_plan_generation`

Training-plan generation becomes an explicit async workflow. It selects an explicit `race_id` when supplied; otherwise it chooses the earliest future primary race, then the earliest future race. If the user has no race, the workflow can generate a base plan when requested.

The LLM proposes a structured draft plan. Johnny validates and stores it as a `draft` training plan, then creates a pending `training_plan_creation` recommendation. The LLM must not directly activate or supersede plans. Acceptance activates the draft and supersedes conflicting active plans.

## Local Automation

Local automation should use a database-backed task queue with an AWS-like task envelope:

- `task_type`
- `correlation_id`
- `idempotency_key`
- `payload`
- `created_at`

The local CLI should support scheduler and worker one-shot, drain, and loop modes. Smoke commands should enqueue all target workflows, process queued work, poll run status, and fail if deterministic runs do not complete within a configurable timeout.

## Approval Gate

This OpenSpec change requires product-owner approval of `design.md` before implementation starts.
