## MODIFIED Requirements

### Requirement: Training Plan Calendar
The system SHALL represent a user's training plan as dated planned workouts tied to a user and optional race goal, with lifecycle states for active, completed, archived, draft, and superseded plans.

#### Scenario: Creating an active generated race plan
- **GIVEN** a user has an athlete profile and a generated race plan
- **WHEN** the generated plan is stored
- **THEN** the system stores the plan with status `active`
- **AND** overlapping active plans for the same race are marked `superseded`

### Requirement: Generated Plan Activation Lifecycle
The system SHALL create generated training plans as active plans immediately.

#### Scenario: Creating generated plan for a race
- **GIVEN** an active plan already exists for a race
- **WHEN** a generated plan is created for the same race
- **THEN** the generated plan is stored as `active`
- **AND** the previous overlapping active plan for that race is marked `superseded`

#### Scenario: Creating base plan without race
- **GIVEN** a generated base plan has no race
- **WHEN** the generated plan is created
- **THEN** the base plan is stored as `active`

#### Scenario: Preserve other race plans
- **GIVEN** an active plan exists for a different race
- **WHEN** a generated plan is created for another race
- **THEN** the other race plan remains `active`

#### Scenario: Preserve non-overlapping plan for same race
- **GIVEN** an active plan exists for the same race in a non-overlapping date range
- **WHEN** a generated plan is created for that race
- **THEN** the non-overlapping race plan remains `active`
