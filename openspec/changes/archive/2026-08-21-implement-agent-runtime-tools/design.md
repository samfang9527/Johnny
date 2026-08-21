## Context

Johnny already has deterministic domain and application boundaries for athlete profiles, race goals, training plans, activity/health data, training analytics, and recommendation approval. The persistence schema also already includes `agent_runs`, `agent_run_steps`, and `agent_context_sources`, so this change should implement runtime behavior over those tables instead of adding a new observability schema.

The current architecture separates application-facing boundary protocols (`Store`/`Provider`) from infrastructure repositories. The agent runtime must follow that boundary: the agent receives context through explicit tools and creates recommendation proposals through application handlers, never by querying or mutating database tables directly.

## Goals / Non-Goals

**Goals:**

- Add one Running Companion Agent runtime suitable for daily scheduled runs and future reactive conversation runs.
- Define structured tool contracts for athlete context, memories, training plan context, today workout, recent activities, recovery state, training metrics, recommendation creation, workout adjustment proposals, and memory candidates.
- Persist every agent run and relevant steps using existing agent run models, including prompt version, trigger, model metadata, tool calls, status, summaries, latency, token usage when available, and recommendation links.
- Keep deterministic analytics outside the LLM. Tools may call analytics handlers or domain services, but the LLM does not compute canonical metrics.
- Enforce a safe proposal boundary: material training-plan changes become pending recommendations or adjustment proposals for user approval.
- Add conservative safety behavior for pain, injury-adjacent, and medical-style prompts.

**Non-Goals:**

- No multi-agent architecture.
- No direct notification delivery.
- No frontend chat UI.
- No direct Garmin, Firebase, or external integration changes.
- No automatic application of significant training changes.

## Decisions

### Use A Single Application-Level Agent Runtime

Implement a `RunningCompanionAgent` or equivalent application handler that coordinates prompt construction, tool execution, model invocation, and run recording. The runtime should depend on application interfaces such as stores, providers, gateways, and a model client protocol.

Alternative considered: embed agent orchestration directly in scheduled jobs or API routes. That would make later model/provider replacement harder and would blur authorization, observability, and tool policies.

### Treat Tool Interfaces As The Agent's Only Data Boundary

Create agent tool contracts with typed inputs and structured payload outputs. Read tools return purpose-specific context, not entire database models. Write tools call recommendation/plan proposal application handlers and return created proposal identifiers and summaries.

Alternative considered: expose repository-like data access to the agent layer. That is rejected because it bypasses tenant checks, approval workflow, and tool-call observability.

### Keep Writes Proposal-Only By Default

The initial write tools may create recommendations, propose workout adjustments, and store memory candidates. They MUST NOT directly mutate planned workouts, completed activities, health metrics, or user profile facts. Existing recommendation approval handlers remain responsible for accepting, rejecting, editing, and applying changes.

Alternative considered: allow low-risk direct writes. That can be revisited later, but the MVP should keep a simple invariant that agent writes are proposals unless explicitly approved by a later change.

### Persist Run Observability Through Existing Models

Use existing `AgentRunModel`, `AgentRunStepModel`, and `AgentContextSourceModel` through a new application-facing `AgentRunStore` and SQLAlchemy repository. Store prompt/model metadata on the run, tool calls as steps, context sources as source rows, and link created recommendations back to the run.

Alternative considered: keep observability only in logs. Logs are useful but insufficient for user-facing traceability, debugging prompt changes, or measuring token/cost trends.

### Isolate Model Provider Behind A Gateway

Define an application-facing model gateway protocol and fake implementation for tests. Production provider selection can be wired later without changing tool contracts or orchestration tests.

Alternative considered: choose a concrete model SDK in this change. That is unnecessary for the MVP runtime tests and would make early code harder to run offline.

### Safety Checks Wrap Agent Output

Safety classification should happen before acting on user text and again before persisting agent-created recommendations. Pain, injury-adjacent, and medical-style requests should receive conservative guidance and escalation language, and they should not produce aggressive workout increases.

Alternative considered: rely entirely on prompt instructions. Prompt-only safety is too brittle for a system that may create actionable training proposals.

## Risks / Trade-offs

- Tool payloads become too broad -> Keep tool outputs purpose-specific and covered by contract tests.
- Fake model tests miss provider quirks -> Start with model gateway contract tests and add provider-specific smoke tests when a real provider is configured.
- Agent recommendations duplicate deterministic rules -> Keep analytics calculation in domain/application services and require evidence references in recommendation payloads.
- Observability records contain too much sensitive text -> Store summaries and structured metadata by default; avoid persisting raw prompts or full health payloads unless explicitly allowed.
- Safety wording is either too vague or too medical -> Use conservative, non-diagnostic language and route urgent symptoms to professional care.

## Migration Plan

1. Add domain/application value objects and protocols for agent runs, tool calls, model gateway responses, and safety decisions.
2. Implement SQLAlchemy persistence for existing agent run tables.
3. Implement read tools over existing application handlers/stores and proposal-only write tools over recommendation approval handlers.
4. Add fake model orchestration tests for daily recommendation and safety scenarios.
5. Wire the runtime behind application handlers without exposing it through public API routes yet.

Rollback is straightforward because the change adds application code and uses existing tables. If runtime behavior is disabled, scheduled/API callers can avoid invoking the agent handler while persisted historical run records remain readable.

## Open Questions

- Which production model provider and model name should be configured first?
- What prompt version naming convention should be used once prompts are stored outside code?
- Which memory candidates should require user confirmation before becoming durable athlete memory?
