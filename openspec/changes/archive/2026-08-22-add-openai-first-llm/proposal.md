## Why

Johnny has a tool-centered agent runtime and fake model gateway, but it does not yet have a concrete production LLM provider. Adding OpenAI as the first provider lets daily recommendations and coach conversations use a real model while preserving the existing domain boundary that keeps LLM calls behind an application-facing gateway.

## What Changes

- Add OpenAI as the first supported production LLM provider for the Running Companion Agent.
- Configure provider selection through environment variables with OpenAI as the first concrete provider and the fake gateway remaining available for tests.
- Map OpenAI responses into Johnny's existing `ModelResponse`, tool-call, token-usage, provider, and model metadata contracts.
- Fail safely when OpenAI configuration or invocation fails, recording failed agent runs without creating successful recommendations.
- Document the local configuration needed to enable OpenAI-backed agent execution.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `agent-runtime-tools`: Extend the model gateway isolation requirement from fake-only orchestration to include OpenAI as the first production LLM provider behind the same gateway contract.

## Impact

- Backend infrastructure gains an OpenAI model gateway adapter and dependency.
- Backend configuration and `.env.example` gain OpenAI provider/model/key settings.
- Agent runtime composition gains provider selection while preserving the existing `ModelGateway` protocol.
- Unit tests cover request mapping, tool-call parsing, token usage, safe configuration errors, and failure recording.
- README or backend documentation gains OpenAI setup guidance for local development.
