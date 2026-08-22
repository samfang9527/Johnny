## ADDED Requirements

### Requirement: OpenAI Model Gateway Provider
The system SHALL provide OpenAI as the first production LLM provider behind the existing application-facing model gateway contract.

#### Scenario: OpenAI gateway completes a model request
- **WHEN** the Running Companion Agent submits a model request through an OpenAI-configured gateway
- **THEN** the gateway sends the request to OpenAI using the configured model
- **AND** it returns a Johnny `ModelResponse` containing provider `openai`, model metadata, response content, parsed tool calls, and token usage when available

#### Scenario: Domain remains provider independent
- **WHEN** OpenAI-backed agent execution is configured
- **THEN** Johnny domain models and agent tool contracts do not depend on OpenAI SDK types
- **AND** provider-specific mapping remains isolated to infrastructure or composition code

### Requirement: Configurable LLM Provider Selection
The system SHALL select the production model gateway from runtime configuration while preserving fake gateway usage for tests.

#### Scenario: OpenAI provider is configured
- **WHEN** runtime configuration selects OpenAI and supplies the required API key and model settings
- **THEN** the application composes `RunningCompanionAgent` with the OpenAI model gateway
- **AND** persisted agent runs record OpenAI provider and model metadata

#### Scenario: Tests use fake gateway
- **WHEN** unit or integration tests construct agent orchestration without OpenAI credentials
- **THEN** they can continue using the fake model gateway without network access
- **AND** no OpenAI API request is required for deterministic test coverage

### Requirement: Safe OpenAI Failure Handling
The system SHALL fail OpenAI-backed agent runs safely when provider configuration or invocation fails.

#### Scenario: OpenAI configuration is incomplete
- **WHEN** runtime configuration selects OpenAI without required credential or model settings
- **THEN** the system refuses to construct or run the OpenAI gateway
- **AND** it reports a safe configuration error that does not expose secret values

#### Scenario: OpenAI invocation fails
- **WHEN** OpenAI model invocation fails during an agent workflow
- **THEN** the agent run is marked failed through the existing run store behavior
- **AND** the run records a safe error type and summary
- **AND** no successful recommendation is linked to the failed run
