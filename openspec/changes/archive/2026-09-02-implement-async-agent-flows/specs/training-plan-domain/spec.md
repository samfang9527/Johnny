## MODIFIED Requirements

### Requirement: Training Plan Calendar
The system SHALL represent a user's training plan as dated planned workouts tied to a user and optional race goal, with lifecycle states for active, completed, archived, draft, and superseded plans.

#### Scenario: Creating a manual plan
- **GIVEN** a user has an athlete profile and optional race goal
- **WHEN** a training plan is created with start date, end date, and dated workouts
- **THEN** the system stores the plan and workouts in calendar order

#### Scenario: Creating a draft generated plan
- **GIVEN** a user has an athlete profile and a generated race or base plan proposal
- **WHEN** the draft plan is stored
- **THEN** the system stores the plan with status `draft`
- **AND** it is not treated as an active plan for daily recommendation scheduling

#### Scenario: Rejecting invalid plan date range
- **WHEN** a training plan is created with an end date before the start date
- **THEN** the system rejects the training plan with a validation error

#### Scenario: Rejecting workout outside plan boundaries
- **WHEN** a workout is scheduled before the plan start date or after the plan end date
- **THEN** the system rejects the training plan with a validation error

## ADDED Requirements

### Requirement: Draft Plan Activation Lifecycle
The system SHALL activate generated draft training plans only through recommendation approval.

#### Scenario: Activating draft plan for a race
- **GIVEN** a pending training-plan-creation recommendation references a draft plan for a race
- **WHEN** the user accepts the recommendation before the race date
- **THEN** the draft plan becomes `active`
- **AND** active plans for the same race are marked `superseded`

#### Scenario: Activating base plan without race
- **GIVEN** a pending training-plan-creation recommendation references a draft base plan without a race
- **WHEN** the user accepts the recommendation
- **THEN** the draft plan becomes `active`
- **AND** active plans with overlapping dates for that user are marked `superseded`

#### Scenario: Reject stale generated race plan
- **GIVEN** a draft race plan is referenced by a pending recommendation
- **WHEN** the user attempts to accept the recommendation after the race date
- **THEN** the system rejects activation
- **AND** the draft remains inactive

#### Scenario: Block newer active plan conflict
- **GIVEN** a newer active plan for the same race was created after the recommendation
- **WHEN** the user attempts to accept the older generated plan recommendation
- **THEN** the system rejects activation
- **AND** no existing plan is superseded
