## MODIFIED Requirements

### Requirement: Tool-Centric Agent Access
The system SHALL require the Running Companion Agent to access athlete, training, recovery, metric, recommendation, memory, and generated-plan draft data through explicit domain tools.

#### Scenario: Agent needs recovery context
- **WHEN** the agent needs recovery context for a user and date
- **THEN** it calls a recovery or today-context tool
- **AND** it receives structured recovery fields and unavailable-signal metadata
- **AND** it does not directly query database tables

#### Scenario: Agent needs recent training history
- **WHEN** the agent needs recent activity or training-load context
- **THEN** it calls a training history or metrics tool with a trusted `user_id` and date window
- **AND** the tool returns only records scoped to that user

#### Scenario: Agent creates a generated training plan draft
- **WHEN** the training-plan generation workflow needs to persist a proposed plan
- **THEN** it uses the `createDraftTrainingPlan` tool
- **AND** the tool validates and stores a draft plan scoped to the trusted user
- **AND** the tool does not activate or supersede existing plans

### Requirement: Proposal-Only Write Tools
The system SHALL allow the agent to create recommendations, workout adjustment proposals, memory candidates, and draft training plans but MUST NOT directly apply significant training-plan changes.

#### Scenario: Agent recommends reducing a workout
- **GIVEN** the agent recommends reducing tomorrow's workout
- **WHEN** it invokes the workout adjustment write tool
- **THEN** the system creates a pending recommendation or proposal for user approval
- **AND** the planned workout remains unchanged until the user accepts the proposal

#### Scenario: Agent proposes a new training plan
- **WHEN** the agent generates a new race or base training plan
- **THEN** the system stores the plan with status `draft`
- **AND** it creates a pending `training_plan_creation` recommendation
- **AND** no draft plan becomes active until the user accepts that recommendation

#### Scenario: Agent has no safe plan change
- **WHEN** the agent decides no training-plan mutation is appropriate
- **THEN** it may create an informational or no-plan-change recommendation with evidence
- **AND** no workout or plan row is mutated

### Requirement: Agent Run Observability
The system SHALL record each agent run with trigger, workflow name, model provider, model name, prompt version, context summary, tool calls, result status, latency, token usage when available, and related recommendation IDs, including queued async runs.

#### Scenario: Async agent run is queued
- **WHEN** an async product workflow is triggered
- **THEN** the system stores an agent run with status `queued`
- **AND** it links the queued task to the run through the task payload
- **AND** clients can poll the run before worker execution starts

#### Scenario: Daily agent run completes
- **WHEN** a scheduled daily recommendation agent run completes
- **THEN** the system stores an agent run record
- **AND** it stores tool calls as ordered run steps
- **AND** it links any created recommendation to the agent run

#### Scenario: Agent run fails
- **WHEN** model invocation, tool execution, task payload validation, or workflow dispatch fails
- **THEN** the system marks the agent run as failed
- **AND** it records an error type and safe error summary
- **AND** it does not leave a successful recommendation linked to the failed run

## ADDED Requirements

### Requirement: Training Plan Generation Workflow
The system SHALL provide a `training_plan_generation` workflow that creates a validated draft plan and pending approval recommendation.

#### Scenario: Race plan generated from explicit race
- **GIVEN** the current user has an athlete profile and the requested future race
- **WHEN** the training-plan generation workflow runs with `plan_type` `race` and an explicit `race_id`
- **THEN** the workflow uses that race as the plan target
- **AND** creates a draft training plan and pending training-plan-creation recommendation

#### Scenario: Race plan generated from next primary race
- **GIVEN** the current user has an athlete profile and future race goals
- **WHEN** the workflow runs without an explicit `race_id`
- **THEN** it selects the earliest future primary race when one exists
- **AND** otherwise selects the earliest future race

#### Scenario: Base plan generated without race
- **GIVEN** the current user has an athlete profile and no race goal
- **WHEN** the workflow runs with `plan_type` `base`
- **THEN** it creates an 8-week base training plan draft
- **AND** creates a pending training-plan-creation recommendation

#### Scenario: Invalid generated plan is repaired once
- **WHEN** the model proposes an invalid generated training plan
- **THEN** the workflow asks the model to repair once using the original request and validation errors
- **AND** it fails the run with inspectable step details if the repaired output is still invalid

### Requirement: Local Deterministic Agent Flow
The system SHALL support deterministic local agent behavior for every MVP workflow without requiring network access.

#### Scenario: Local training plan generation
- **WHEN** local deterministic mode runs `training_plan_generation`
- **THEN** it creates a valid 4-week draft plan with 3-5 workouts per week
- **AND** it creates a pending recommendation that links to the draft plan

#### Scenario: Live OpenAI smoke remains opt-in
- **WHEN** live OpenAI smoke is requested
- **THEN** the caller must provide configured provider, model, and credential settings
- **AND** the smoke command can choose which workflow to exercise
