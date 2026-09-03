## MODIFIED Requirements

### Requirement: Training Plan Generation Workflow
The system SHALL provide a `training_plan_generation` workflow that creates a validated active plan with detailed key-workout steps when sufficient context is available.

#### Scenario: Generation request preloads planning context
- **WHEN** the training-plan generation workflow builds the model request
- **THEN** it preloads athlete profile, athlete baseline, races, recent activity summary, limited key activity records, current or last active plan context, and deterministic pace profile
- **AND** read tools remain available for the model to request extra context

#### Scenario: LLM generates structured workout intent
- **WHEN** the model creates a training plan
- **THEN** it selects phases, weekly logic, workout types, workout steps, target zones, and optional coach notes
- **AND** it persists the plan through `createTrainingPlan`
- **AND** it does not treat exact pace math as authoritative

#### Scenario: Write tool enriches target snapshots
- **WHEN** `createTrainingPlan` receives workout steps with target zones
- **THEN** it computes pace, heart-rate, or RPE snapshots from trusted application context
- **AND** it stores both the original target intent and computed snapshot when confidence allows

#### Scenario: Invalid detailed plan is repaired once
- **WHEN** the model proposes invalid workout steps, invalid totals, or invalid plan metadata
- **THEN** the workflow asks the model to repair once using validation errors
- **AND** if the repaired output remains invalid, the application creates an athlete-adjusted deterministic fallback plan

### Requirement: Local Deterministic Agent Flow
The system SHALL support deterministic local agent behavior for detailed training-plan generation without requiring network access.

#### Scenario: Local detailed training plan generation
- **WHEN** local deterministic mode runs `training_plan_generation`
- **THEN** it creates a valid active plan containing structured steps for interval, tempo, and threshold-style key workouts
- **AND** it includes deterministic summaries, target snapshots when confidence allows, coach notes, phases, and plan continuity metadata
