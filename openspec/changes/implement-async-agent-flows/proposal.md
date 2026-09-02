## Why

Johnny's MVP loop depends on agent workflows that can be called through APIs, persisted for observability, executed asynchronously, and tested locally before moving to AWS scheduling and queue infrastructure. The current codebase has the core Running Companion Agent, local/OpenAI model gateways, recommendation approval, training plan persistence, and basic API routes, but async execution is still template-level: the dispatcher publishes an example task to an in-memory queue and the worker only logs tasks.

This change completes the end-to-end agent flow for local MVP validation while preserving the intended production direction: EventBridge/EventBus-style scheduling, SQS-compatible task envelopes, Lambda-style workers, and explicit user approval before significant training-plan mutation.

## What Changes

- Add async product endpoints for `daily_recommendation` and `training_plan_generation`.
- Keep `coach_conversation` synchronous through the existing conversation endpoint for current UX.
- Add user-scoped agent run read APIs for polling run status and ordered steps.
- Add a database-backed local `agent_tasks` queue with AWS-like envelope fields, idempotency, retry metadata, claiming, retry delay, and dead-letter state.
- Add local scheduler and worker CLI modes for one-shot, drain, and loop operation.
- Extend agent run lifecycle to support queued runs.
- Add training-plan draft lifecycle support with `draft` and `superseded` plan statuses.
- Add recommendation approval support for generated draft plans through a `training_plan_creation` recommendation and a `create_training_plan` proposed action.
- Add a `training_plan_generation` workflow that creates a draft plan and pending recommendation through validated tools.
- Add deterministic local gateway behavior for training-plan generation so local smoke tests can run without network access.
- Add tests for queue persistence, scheduler eligibility, worker execution, async APIs, training-plan approval, and deterministic smoke behavior.
- Update README, manual runbook, and architecture documentation for local async agent operation and opt-in live OpenAI smoke tests.

## Capabilities

### Modified Capabilities

- `agent-runtime-tools`: Async workflow orchestration, training-plan generation, tool allowlists, deterministic local behavior, repair loop, and observability.
- `backend-api`: Async trigger endpoints, compact queued responses, run polling, and run step inspection.
- `training-plan-domain`: Draft and superseded plan lifecycle for generated plans.
- `recommendation-approval`: Approval behavior for training-plan creation recommendations.
- `persistence-schema`: Agent task queue table, queued run status, plan/recommendation status constraints, and migration coverage.

## Impact

- Affects backend domain models, application agent orchestration, API schemas/routes, persistence models/repositories, Alembic migrations, local scripts, Makefile targets, tests, and documentation.
- Keeps normal tests network-free by using deterministic local or fake model gateways.
- Keeps live OpenAI execution opt-in and configurable.
- Does not add production AWS infrastructure, LocalStack, cancellation, public task inspection APIs, frontend implementation, or direct LLM activation of training plans.
