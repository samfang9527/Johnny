## Context

Johnny's agent runtime already depends on an application-facing `ModelGateway` protocol. `RunningCompanionAgent` builds workflow-specific `ModelRequest` objects, executes returned tool calls through `AgentToolRegistry`, and persists provider/model metadata, token usage, tool steps, context sources, failures, and recommendation links through the agent run store.

The current implementation includes only `FakeModelGateway`, which is appropriate for offline tests but cannot power production recommendations or coach conversations. The project direction also says the LLM provider must remain an infrastructure adapter, not a domain dependency. This change should therefore add OpenAI as the first concrete provider without changing domain models, tool contracts, or recommendation approval behavior.

## Goals / Non-Goals

**Goals:**

- Add an OpenAI-backed implementation of the existing `ModelGateway` protocol.
- Use provider configuration to construct `RunningCompanionAgent` with either the fake/test gateway or OpenAI gateway.
- Preserve existing tool-centered orchestration: the model requests tool calls by name, and Johnny executes tools through application contracts.
- Persist OpenAI provider/model metadata, token usage, and safe failure summaries through the existing agent run behavior.
- Keep local development explicit: OpenAI execution requires configured provider, model, and API key values.

**Non-Goals:**

- No new domain dependency on OpenAI types.
- No direct training-plan mutation by model output.
- No multi-provider routing beyond the first OpenAI provider and the existing fake/test gateway.
- No streaming, background responses, retrieval, image/audio input, or hosted agent migration.
- No public API route or scheduler change unless needed to compose the gateway behind an existing handler.

## Decisions

### Use an infrastructure `OpenAIModelGateway`

Implement the provider under backend infrastructure, for example `src.infrastructure.llm.openai_gateway.OpenAIModelGateway`, and keep `src.application.interfaces.agent_runtime.ModelGateway` unchanged. The adapter translates Johnny's `ModelRequest` into an OpenAI Responses API request and translates the response back into Johnny's `ModelResponse`.

Alternative considered: put OpenAI calls inside `RunningCompanionAgent`. That would make tests harder, mix provider details into application orchestration, and weaken the current replacement boundary.

Alternative considered: adopt the OpenAI Agents SDK for orchestration. Johnny already has explicit tool, safety, recommendation, and persistence boundaries; replacing that orchestration now would add scope and obscure which code owns approvals.

### Keep provider selection in composition/configuration

Add a small configuration resolver that reads `LLM_PROVIDER`, `LLM_MODEL`, and API key settings. `LLM_PROVIDER=openai` selects `OpenAIModelGateway`; tests continue constructing `FakeModelGateway` directly. The adapter should accept the API key as an injected value and may fall back to the standard `OPENAI_API_KEY` environment variable for local convenience.

Alternative considered: make OpenAI the unconditional default. That would break offline development and test runs when no key is present. OpenAI should be the first production provider, not a requirement for all runtime construction.

### Map only Johnny-supported tool calls

The gateway should expose Johnny tools as OpenAI function tools using the names already returned by `AgentToolRegistry.names()`. Tool schemas can start minimal and conservative: each tool accepts an object payload, the registry remains the authoritative executor, and unknown or malformed calls fail the run safely.

Alternative considered: create rich JSON schemas for every tool in the first pass. That is useful later, but a minimal schema is enough to preserve the current contract and avoid duplicating validation rules already enforced by tools and domain constructors.

### Normalize response metadata and errors

The adapter returns `provider="openai"`, the configured or returned model name, response content, parsed tool calls, and token usage when the API supplies it. Provider exceptions are wrapped in a local gateway error with a safe summary so `RunningCompanionAgent` can mark the run failed without leaking secrets or raw provider payloads.

Alternative considered: let OpenAI SDK exceptions bubble unchanged. That risks inconsistent error summaries and accidental exposure of request metadata in persisted run records.

## Risks / Trade-offs

- OpenAI request/response shapes can evolve -> keep all SDK-specific parsing isolated in one adapter and cover it with unit tests using lightweight fake response objects.
- Minimal tool schemas may produce malformed arguments -> fail safely and rely on existing tool/domain validation; add richer schemas in a later focused change if malformed calls become common.
- API keys may be missing or misconfigured -> validate configuration before constructing the gateway and document local setup in `.env.example`/README.
- Network-backed tests can become flaky -> keep normal unit tests offline with a fake OpenAI client; make any live smoke test opt-in through an environment variable.
- OpenAI retention/data-control settings may matter for athlete context -> send only the structured context already approved for agent prompts and avoid adding unrelated personal data to provider payloads.

## Migration Plan

1. Add the OpenAI SDK dependency to backend requirements.
2. Add OpenAI LLM configuration values to `backend/.env.example` and local documentation.
3. Implement `OpenAIModelGateway` and provider configuration/composition.
4. Add offline unit tests for request mapping, tool-call parsing, token usage mapping, configuration validation, and safe failure handling.
5. Keep existing fake-gateway tests unchanged so agent orchestration remains deterministic.

Rollback is straightforward: set `LLM_PROVIDER` away from `openai` or remove OpenAI gateway composition. The database schema and persisted historical agent runs remain compatible because provider/model/token fields already exist.

## Open Questions

- Which exact OpenAI model should be the initial configured default for Johnny deployments?
- Should a later change add strict per-tool JSON schemas once OpenAI-backed usage reveals the most common malformed-call cases?
