# Training Plan Regeneration Boundaries and Live LLM

## Purpose

Make UI-triggered training-plan regeneration follow Johnny's Route -> CQRS handler -> domain model/policy -> data-access seam, then verify a real OpenAI-generated result through that same production queue and worker path. This work does not change the athlete-facing regeneration contract, quota, safety rules, or canonical Plan Skeleton.

The existing training-plan generation spec and skeleton ADR remain authoritative for workout completeness and activation. This spec only covers regeneration ownership, provider selection, and live verification.

## Current State and Boundary Problems

`backend/src/api/routes/training_plan_regeneration.py` builds SQL repositories, a `QueueAgentRunHandler`, and `TrainingPlanRegenerationService` directly. It also locks a `UserModel` row in the route. The application service imports `TrainingPlanRegenerationRequest` from the API schema package. This reverses the intended dependency direction and makes the route responsible for business wiring.

The route's queue handler persists `provider="local"` and `model="deterministic-local-companion"`; the raw training-plan agent-run route and scheduler do the same. `scripts/agent_runtime.py` dispatches using the queued run's provider and model, so a configured OpenAI key does not change a UI regeneration into an OpenAI run. The CLI also clears `LLM_PROVIDER` for non-smoke commands, while the current settings loader requires that variable even when a key and model are present. Today, `build_request_companion_agent(provider="local")` correctly selects the local gateway; a request for OpenAI must not silently fall back to local when worker credentials are unavailable or silently use a newer configured model.

## Desired Architecture

### Route and Composition

The regeneration route validates HTTP input, invokes a query or command handler supplied by FastAPI dependency composition, and maps the handler result to the existing response schema. It does not import `src.infrastructure.*`, SQLAlchemy models or queries, or construct repositories or queue handlers. User authentication remains at the API boundary; user existence and per-user serialization needed for queueing happen behind the handler's injected ports.

The composition root (`src.api.dependencies` or a dedicated API composition module) constructs concrete SQL adapters and handlers from the request session. This is the only API-side place that knows both application ports and infrastructure implementations. Request-scoped session commit/rollback remains the transaction boundary. Existing user bootstrap can remain in an auth dependency. The `GET /regeneration-options` query performs no regeneration mutation; the `POST /regenerations` command holds the user lock while reading quota/in-flight state and queueing, preserving atomic idempotency.

### CQRS Handlers and Domain Model

Define a query handler for regeneration options and a command handler for starting regeneration. Both accept transport-independent inputs: `user_id`, dates or clock, and a domain/application request value containing `client_request_id`, `plan_type`, and optional `race_id`. Neither application handler imports API schemas or SQL adapters. Explicit repository/queue/user-lock protocols describe the data access it needs; avoid a generic repository or broad Unit of Work rewrite.

Reuse the existing `TrainingPlan` aggregate and `TrainingPlanStore` seam for current-plan lookup and projection invariants. A separate, pure regeneration decision policy consumes Athlete Baseline, future Race Strategies, relevant Agent Runs, and the current Active Projection. It decides default strategy, athlete-local quota day, quota consumption, same-request reuse, in-flight reuse, and whether a new run may be queued. It returns a decision and queue intent, not a SQL operation or HTTP response. The application handler loads a consistent snapshot, calls the policy, then performs the chosen queue action through a port. There is no new aggregate or table: run history and quota do not become fields on `TrainingPlan`, and merely queueing does not mutate a plan. Background discovery uses the same pure strategy rules without forcing its separate recovery-window workflow into the manual command handler.

Keep current rules: explicit maintenance is valid even with future races; current future strategy is the default; priority then date selects other races; tomorrow is the manual start; one successful manual activation per athlete-local day consumes quota; same `client_request_id` returns the same run; any other in-flight run is reused; quota exhaustion returns `run: null`; background generation does not consume manual quota. A completed, fully validated new projection supersedes the old one only in its existing save transaction. No migration or API response shape change is expected.

### Provider Selection and Dispatch

At queue time, production composition reads the existing key/model configuration and selects a provider for this run:

- A nonempty `LLM_API_KEY` or `OPENAI_API_KEY` plus a configured `LLM_MODEL` queues `provider="openai"` and that model, even when `LLM_PROVIDER` is unset. Keep the existing key precedence (`LLM_API_KEY` first). A key with no model is a configuration error, not a local fallback.
- With neither key, queue `provider="local"` and `model="deterministic-local-companion"`, even if an OpenAI provider name remains in development configuration. Unsupported explicit provider values remain configuration errors.
- Persist provider/model on the queued Agent Run. Reused idempotent and in-flight runs retain their original provider/model; changing environment variables must not mutate them.
- The worker dispatches by the persisted provider. A queued OpenAI run uses its persisted model and a runtime key, not a model name changed in the worker environment. If the worker lacks the key, fails authentication, or cannot call the model, record a failed run/task with a redacted diagnostic; never run the local gateway as if this were a successful OpenAI result. Existing queued local runs remain local.
- `work-one`, `work-drain`, and `work-loop` must preserve the configuration required for an OpenAI run. They must not erase `LLM_PROVIDER` before provider resolution. The UI regeneration route, raw training-plan agent-run route, and scheduler use the same provider-selection policy rather than diverging queue defaults. Unrelated daily-recommendation and conversation provider behavior is not expanded by this spec.

No key or model is stored in Agent Run metadata, response bodies, exception text, or logs. An API process with the key can queue OpenAI, but its worker also needs access to the key; the persisted provider selection makes a mismatch observable rather than silently changing behavior. A key being present intentionally opts this deployment into paid generation when work is processed.

## Live Verification

Run only after implementation and tests pass. Use the existing isolated PostgreSQL and live-LLM runbooks, revised to remove the patched adapter as the success path. Do not use the developer's current `johnny` database or existing athlete data. Prepare one disposable PostgreSQL database and one synthetic athlete with a conservative baseline, then use the real `POST /api/v1/training-plans/regenerations` endpoint, production `work-one` or `work-drain`, and `GET /api/v1/agent-runs/{id}` plus `/steps` and the saved plan endpoint.

Before the paid call, verify the configured model, the key's presence without displaying it, an operator-approved call/cost limit, the container/database identity, and the absence of unrelated queued tasks. Set `ENV=test` so the disposable test process does not load the normal development `.env`; inject the key into only the dedicated test API/worker environments without recording it. Make one sample first; do not run all six runbook scenarios automatically. Record redacted run/step/plan evidence and model token usage if returned. A completed run is not enough: inspect phase coverage, every week's workouts, hard-session limits, Workout Steps/Targets, and completion repair/fallback metadata. Report a deterministic fallback separately from valid LLM enrichment.

The Python SDK's Responses API is the live gateway already used by Johnny; follow the [official OpenAI text-generation documentation](https://developers.openai.com/api/docs/guides/text). The local `.env` or shell provides the key; never copy its value into a script, test fixture, spec, command output, or commit.

## Verification and Acceptance

1. Static boundary test or import check proves the regeneration route does not import infrastructure/SQLAlchemy, and application/domain regeneration code does not import `src.api` or `src.infrastructure`. Both plan CRUD and regeneration use the existing `TrainingPlan` model/repository rather than duplicating them.
2. Existing route and service tests retain options, manual request, race selection, idempotency, in-flight, quota, and activation behavior. Add domain-decision tests independent of database and handler tests using injected ports.
3. Provider tests cover: key+model queues OpenAI even without `LLM_PROVIDER`; no key queues local; key without model errors; existing local run stays local; reused run keeps its provider; missing worker key for an OpenAI run fails visibly without invoking the local gateway; a worker model setting change does not change an already queued run. Verify UI, raw training-plan API, background queueing, and CLI worker modes.
4. Full backend suite passes. Frontend contract and tests remain unchanged unless an actual response compatibility issue is found.
5. PostgreSQL integration proves queue and worker use the same isolated database. A single authorized live run through the unpatched production path records provider/model and yields a fully validated saved projection or a clearly classified failure. Do not label a local fallback, mock, or patched composition as a live production pass.

## Work Breakdown

- Stage A: Introduce domain regeneration decision model and application query/command handlers; move wiring to composition and thin the route. Preserve provider behavior during this stage.
- Stage B: Add configuration-based provider selection, persist it at queue time, and make worker dispatch fail explicitly when a selected OpenAI provider cannot be used. Cover manual and background runs.
- Stage C: Update runbooks, run the isolated PostgreSQL checks, then execute one approved paid OpenAI sample and report the real output/limitations. Perform only one stage at a time.

## Out of Scope

Changing plan-generation prompts, LLM model selection, workout safety policy, quota product tiers, frontend layout, or production secret management. A paid call is not executed merely by writing this spec.
