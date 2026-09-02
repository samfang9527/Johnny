## Purpose
Define the training plan domain behavior for dated planned workouts, workout status lifecycle, adjustment proposals, and repository persistence mapping.

## Requirements

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

### Requirement: Workout Details
The system SHALL represent MVP planned workout details needed by future Today, analytics, and recommendation workflows.

#### Scenario: Creating a planned run workout
- **WHEN** a workout is created with supported type, purpose, scheduled date, planned distance or duration, optional pace range, and optional heart-rate zone
- **THEN** the system stores the workout details as a valid planned workout

#### Scenario: Rejecting unsupported workout type
- **WHEN** a workout is created with an unsupported workout type
- **THEN** the system rejects the workout with a validation error

#### Scenario: Rejecting workout without planned load
- **WHEN** a workout is created without planned distance and without planned duration
- **THEN** the system rejects the workout with a validation error

### Requirement: Workout Status Lifecycle
The system SHALL track workout status through controlled lifecycle transitions.

#### Scenario: Completing a planned workout
- **GIVEN** a planned workout exists
- **WHEN** the workout is marked completed
- **THEN** the system records completed status and preserves the original planned workout details

#### Scenario: Skipping a planned workout
- **GIVEN** a planned workout exists
- **WHEN** the workout is marked skipped
- **THEN** the system records skipped status and preserves the original planned workout details

#### Scenario: Rejecting invalid workout status transition
- **GIVEN** a completed workout exists
- **WHEN** the workout is changed back to planned
- **THEN** the system rejects the transition with a validation error

### Requirement: Plan Adjustment Proposal
The system SHALL represent proposed workout changes separately from applied workout changes.

#### Scenario: Proposing a shorter workout
- **GIVEN** a planned workout exists
- **WHEN** an adjustment is proposed with before and after workout details
- **THEN** the system stores the adjustment proposal without changing the workout

#### Scenario: Approving an adjustment proposal
- **GIVEN** a proposed adjustment exists
- **WHEN** the adjustment is approved
- **THEN** the system records approved status without applying workout mutation

#### Scenario: Rejecting an adjustment proposal
- **GIVEN** a proposed adjustment exists
- **WHEN** the adjustment is rejected
- **THEN** the system records rejected status without applying workout mutation

### Requirement: Training Plan Persistence Mapping
The system SHALL persist training plan domain objects through repository methods using the existing persistence schema.

#### Scenario: Loading persisted plan with workouts
- **WHEN** a training plan with workouts is saved and later loaded by user id
- **THEN** the loaded domain object contains the same plan dates, optional race id, ordered workouts, statuses, and planned workout details

#### Scenario: Loading persisted adjustment proposals
- **WHEN** an adjustment proposal is saved and later listed for a user-scoped plan
- **THEN** the loaded proposal contains the same before payload, after payload, status, and linked plan/workout identifiers

#### Scenario: Enforcing plan ownership
- **WHEN** a repository operation loads or updates a training plan by id for a different user
- **THEN** the system does not return or mutate that training plan

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
