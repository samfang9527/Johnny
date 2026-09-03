# athlete-race-domain Specification

## Purpose
Define the athlete and race domain objects Johnny uses for training planning, including baseline training context, target race metadata, validation, and persistence behavior.

## Requirements

### Requirement: Athlete Profile
The system SHALL represent a runner's baseline training context for training decisions.

#### Scenario: Creating an athlete profile
- **WHEN** a user provides timezone, nullable experience level, current weekly mileage in canonical kilometers, preferred training days, preferred long-run day, maximum runs per week, unit preference, and injury context
- **THEN** the system stores a valid athlete profile for that user

#### Scenario: Rejecting invalid weekly mileage
- **WHEN** a user provides a negative current weekly mileage value
- **THEN** the system rejects the athlete profile with a validation error

#### Scenario: Updating athlete preferences
- **WHEN** a user changes preferred training days, preferred long-run day, maximum runs per week, unit preference, training preferences, injury status, injury areas, or injury notes
- **THEN** the system persists the updated preferences without requiring a race goal change

### Requirement: Race Goal
The system SHALL represent a target race with date, distance, optional target finish time, priority, and status.

Race priority SHALL be one of `primary`, `secondary`, or `tune_up`.

#### Scenario: Creating a race goal
- **WHEN** a user with an athlete profile creates a race goal with name, future date, distance, and optional target finish time
- **THEN** the system stores the race goal for that user with planned status

#### Scenario: Deriving target average pace
- **WHEN** a race goal has distance and target finish time
- **THEN** the system derives target average pace from the target finish time divided by distance

#### Scenario: Creating a race goal without target finish time
- **WHEN** a user creates a race goal without target finish time
- **THEN** the system stores the race goal and leaves target average pace unset

### Requirement: Domain Validation
The system SHALL reject athlete and race values that would make training planning invalid.

#### Scenario: Invalid race date
- **WHEN** a user creates a race with a date before the validation date
- **THEN** the system rejects the race goal with a validation error

#### Scenario: Invalid race distance
- **WHEN** a user creates a race with a distance less than or equal to zero meters
- **THEN** the system rejects the race goal with a validation error

#### Scenario: Invalid preferred long-run day
- **WHEN** a user selects preferred training days and sets the preferred long-run day outside that set
- **THEN** the system rejects the athlete preferences with a validation error

#### Scenario: Empty preferred training days
- **WHEN** a user leaves preferred training days empty
- **THEN** the system stores the profile and allows plan generation to choose training days

### Requirement: Persistence Mapping
The system SHALL persist athlete profile and race goal domain objects through repository methods using the existing persistence schema.

#### Scenario: Loading persisted athlete profile
- **WHEN** an athlete profile is saved and later loaded by user id
- **THEN** the loaded domain object contains the same validated training context and preferences

#### Scenario: Loading persisted race goals
- **WHEN** race goals are saved and later listed by user id
- **THEN** the loaded domain objects contain the same race date, distance, status, priority, target finish time, and derived pace values

#### Scenario: Enforcing race ownership
- **WHEN** a repository operation loads or updates a race goal by id for a different user
- **THEN** the system does not return or mutate that race goal
