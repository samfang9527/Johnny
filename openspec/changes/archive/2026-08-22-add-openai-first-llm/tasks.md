## 1. Dependencies And Configuration

- [x] 1.1 Add the OpenAI Python SDK to backend requirements.
- [x] 1.2 Add `LLM_PROVIDER`, `LLM_MODEL`, and OpenAI API key guidance to backend environment examples without committing secrets.
- [x] 1.3 Implement a backend LLM settings resolver that validates OpenAI provider, model, and key configuration and emits safe errors for missing values.

## 2. OpenAI Gateway Adapter

- [x] 2.1 Create an infrastructure `OpenAIModelGateway` that implements the existing `ModelGateway.complete` contract.
- [x] 2.2 Map Johnny `ModelRequest` messages, context, and tool names into an OpenAI Responses API request.
- [x] 2.3 Parse OpenAI response content, function tool calls, model metadata, and token usage into Johnny `ModelResponse`, `ToolCallRequest`, and `TokenUsage` objects.
- [x] 2.4 Wrap OpenAI SDK and mapping failures in safe local gateway errors that do not include API keys or raw sensitive payloads.

## 3. Agent Composition

- [x] 3.1 Add composition code that builds `RunningCompanionAgent` with `OpenAIModelGateway` when `LLM_PROVIDER=openai`.
- [x] 3.2 Preserve direct fake-gateway construction for unit tests and offline orchestration tests.
- [x] 3.3 Ensure completed OpenAI-backed runs persist provider `openai`, model name, token usage, tool steps, and recommendation links through existing run-store behavior.
- [x] 3.4 Ensure OpenAI invocation failures mark runs failed and do not link successful recommendations.

## 4. Verification

- [x] 4.1 Add offline unit tests for OpenAI request construction, function tool schema construction, tool-call parsing, and token usage mapping.
- [x] 4.2 Add configuration tests for missing provider, missing model, missing key, and valid OpenAI settings.
- [x] 4.3 Add agent-runtime tests proving OpenAI gateway failures use existing failed-run behavior without successful recommendation links.
- [x] 4.4 Run focused backend tests for agent runtime, OpenAI gateway, configuration, and existing fake-gateway orchestration.

## 5. Documentation

- [x] 5.1 Document local OpenAI setup in README or backend development docs.
- [x] 5.2 Document that live OpenAI smoke testing is opt-in and normal tests remain network-free.
