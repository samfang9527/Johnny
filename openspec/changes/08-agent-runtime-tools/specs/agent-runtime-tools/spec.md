# Delta for Agent Runtime and Tools

## ADDED Requirements

### Requirement: Tool-Centric Agent Access

The system SHALL require the Running Companion Agent to access application data through domain tools.

#### Scenario: Agent needs recovery context

- WHEN the agent needs recovery context
- THEN it calls a recovery tool
- AND it does not directly query database tables

### Requirement: Agent Run Observability

The system SHALL record each agent run with trigger, model, prompt version, context summary, tool calls, result, latency, and token usage when available.

#### Scenario: Daily agent run completes

- WHEN a scheduled daily recommendation agent run completes
- THEN the system stores an agent run record linked to any created recommendation

### Requirement: Safe Proposal Boundary

The system SHALL allow the agent to propose significant training changes but not apply them directly.

#### Scenario: Agent recommends reducing a workout

- GIVEN the agent recommends reducing tomorrow's workout
- WHEN it creates a proposed action
- THEN the system stores the proposal for user approval instead of applying it immediately

