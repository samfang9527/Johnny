## MODIFIED Requirements

### Requirement: Tool-Centric Agent Access
The system SHALL require the Running Companion Agent to access athlete, training, recovery, metric, recommendation, memory, and generated training-plan data through explicit domain tools.

#### Scenario: Agent creates a generated training plan
- **WHEN** the training-plan generation workflow needs to persist a generated plan
- **THEN** it uses the `createTrainingPlan` tool
- **AND** the tool validates and stores an active plan scoped to the trusted user
- **AND** overlapping active plans for the same race are marked `superseded`

### Requirement: Write Tool Safety
The system SHALL allow the agent to create recommendations, workout adjustment proposals, memory candidates, and active training plans while keeping recommendation approval separate from training-plan generation.

#### Scenario: Agent proposes a new training plan
- **WHEN** the agent generates a new race or base training plan
- **THEN** the system stores the plan with status `active`
- **AND** it does not create or require a recommendation
- **AND** overlapping active plans for the same race are marked `superseded`

### Requirement: Training Plan Generation Workflow
The system SHALL provide a `training_plan_generation` workflow that creates a validated active plan.

#### Scenario: Race plan generated from explicit race
- **GIVEN** the current user has an athlete profile and the requested future race
- **WHEN** the training-plan generation workflow runs with `plan_type` `race` and an explicit `race_id`
- **THEN** the workflow uses that race as the plan target
- **AND** creates an active training plan

#### Scenario: Base plan generated without race
- **GIVEN** the current user has an athlete profile and no race goal
- **WHEN** the workflow runs with `plan_type` `base`
- **THEN** it creates an active base training plan

### Requirement: Local Deterministic Agent Flow
The system SHALL support deterministic local agent behavior for every MVP workflow without requiring network access.

#### Scenario: Local training plan generation
- **WHEN** local deterministic mode runs `training_plan_generation`
- **THEN** it creates a valid 4-week active plan with 3-5 workouts per week
- **AND** it does not create a recommendation
