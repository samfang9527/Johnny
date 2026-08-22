## Purpose
Define the runtime tool boundaries for Johnny's running companion agent so it can access athlete, training, recovery, metric, recommendation, and memory data through explicit domain tools while keeping plan mutations safe and observable.
## Requirements
### Requirement: Tool-Centric Agent Access
The system SHALL require the Running Companion Agent to access athlete, training, recovery, metric, recommendation, and memory data through explicit domain tools.

#### Scenario: Agent needs recovery context
- **WHEN** the agent needs recovery context for a user and date
- **THEN** it calls a recovery or today-context tool
- **AND** it receives structured recovery fields and unavailable-signal metadata
- **AND** it does not directly query database tables

#### Scenario: Agent needs recent training history
- **WHEN** the agent needs recent activity or training-load context
- **THEN** it calls a training history or metrics tool with a trusted `user_id` and date window
- **AND** the tool returns only records scoped to that user

### Requirement: Deterministic Analytics Boundary
The system SHALL compute canonical training load, recovery state, and today context through deterministic domain or application services rather than relying on LLM-generated calculations.

#### Scenario: Daily agent run builds context
- **WHEN** a daily recommendation run starts
- **THEN** the runtime builds today context through the training analytics application handler
- **AND** the agent prompt or model response references that structured context instead of inventing metric values

### Requirement: Proposal-Only Write Tools
The system SHALL allow the agent to create recommendations and workout adjustment proposals but MUST NOT directly apply significant training-plan changes.

#### Scenario: Agent recommends reducing a workout
- **GIVEN** the agent recommends reducing tomorrow's workout
- **WHEN** it invokes the workout adjustment write tool
- **THEN** the system creates a pending recommendation or proposal for user approval
- **AND** the planned workout remains unchanged until the user accepts the proposal

#### Scenario: Agent has no safe plan change
- **WHEN** the agent decides no training-plan mutation is appropriate
- **THEN** it may create an informational or no-plan-change recommendation with evidence
- **AND** no workout or plan row is mutated

### Requirement: Agent Run Observability
The system SHALL record each agent run with trigger, workflow name, model provider, model name, prompt version, context summary, tool calls, result status, latency, token usage when available, and related recommendation IDs.

#### Scenario: Daily agent run completes
- **WHEN** a scheduled daily recommendation agent run completes
- **THEN** the system stores an agent run record
- **AND** it stores tool calls as ordered run steps
- **AND** it links any created recommendation to the agent run

#### Scenario: Agent run fails
- **WHEN** model invocation or tool execution fails
- **THEN** the system marks the agent run as failed
- **AND** it records an error type and safe error summary
- **AND** it does not leave a successful recommendation linked to the failed run

### Requirement: Model Gateway Isolation
The system SHALL isolate LLM provider calls behind an application-facing gateway contract so orchestration can be tested with fake model responses.

#### Scenario: Agent orchestration test uses fake model
- **WHEN** tests execute a daily recommendation workflow
- **THEN** they provide a fake model gateway response
- **AND** the runtime records the same tool-call and recommendation behavior without requiring network access

### Requirement: Safety Boundaries For Medical And Injury Topics
The system SHALL detect pain, injury-adjacent, and medical-style prompts and respond with conservative non-diagnostic guidance.

#### Scenario: User reports injury symptoms
- **WHEN** the user asks about pain, injury, illness, or medical symptoms
- **THEN** the agent response avoids diagnosis
- **AND** it recommends reducing or stopping training when appropriate
- **AND** it suggests professional medical care for severe, persistent, or concerning symptoms

#### Scenario: Unsafe workout increase is suggested
- **WHEN** a model response proposes an aggressive workout increase despite recovery or injury-adjacent context
- **THEN** the runtime rejects or downgrades the action before persistence
- **AND** no aggressive workout adjustment proposal is created

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

