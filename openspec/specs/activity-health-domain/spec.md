# activity-health-domain Specification

## Purpose
TBD

## Requirements

### Requirement: Activity Recording
The system SHALL record completed running activities with normalized distance, duration, pace, heart rate, elevation, source, and optional matched workout fields.

#### Scenario: Manual activity entry
- **WHEN** a user records a manual run with start time, distance, and duration
- **THEN** the system stores the activity with source `manual` and derives average pace

#### Scenario: Provider activity entry
- **WHEN** a non-manual activity is recorded with source and source activity id
- **THEN** the system stores the activity with provider identity fields preserved for duplicate protection

#### Scenario: Rejecting activity without load
- **WHEN** a completed running activity is recorded without distance or without duration
- **THEN** the system rejects the activity with a validation error

### Requirement: Pace Derivation
The system SHALL derive average pace from distance and duration when average pace is not supplied.

#### Scenario: Deriving average pace
- **WHEN** an activity has distance meters and duration seconds but no average pace
- **THEN** the system calculates average pace in seconds per kilometer

#### Scenario: Preserving supplied average pace
- **WHEN** an activity includes a supplied average pace
- **THEN** the system preserves the supplied pace value if it is valid

### Requirement: Health Metric Recording
The system SHALL record daily health metrics used for recovery context.

#### Scenario: Daily recovery entry
- **WHEN** a user records sleep duration, sleep quality, HRV, HRV baseline, resting heart rate, and stress score for a date
- **THEN** the system stores normalized daily health metric values for that user and date

#### Scenario: Sparse daily recovery entry
- **WHEN** a user records only some supported daily recovery values
- **THEN** the system stores the supplied values and leaves missing values absent

#### Scenario: Rejecting invalid health values
- **WHEN** a user records negative sleep duration, HRV, resting heart rate, or stress score
- **THEN** the system rejects the health metric entry with a validation error

### Requirement: Duplicate Provider Activity Protection
The system SHALL prevent duplicate provider activities while allowing manual activity entries.

#### Scenario: Duplicate provider activity
- **GIVEN** a provider activity exists for a provider connection and source activity id
- **WHEN** the same provider connection and source activity id are recorded again
- **THEN** the system rejects the duplicate provider activity

#### Scenario: Multiple manual activities
- **WHEN** a user records multiple manual activities without source activity ids
- **THEN** the system stores each manual activity independently

### Requirement: Workout Matching
The system SHALL allow a running activity to be matched to a planned workout.

#### Scenario: Matching completed workout by date
- **GIVEN** exactly one planned workout exists for a user on the activity date
- **WHEN** a running activity is recorded for the same date
- **THEN** the system links the activity to that planned workout

#### Scenario: Ambiguous workout match
- **GIVEN** multiple planned workouts exist for a user on the activity date
- **WHEN** a running activity is recorded for the same date
- **THEN** the system leaves the activity unmatched

### Requirement: Activity Health Persistence Mapping
The system SHALL persist activity and health domain objects through repository methods using the existing persistence schema.

#### Scenario: Loading persisted activity
- **WHEN** an activity is saved and later loaded by user id
- **THEN** the loaded domain object contains the same normalized source, timing, distance, duration, pace, heart rate, elevation, and matched workout values

#### Scenario: Loading persisted daily health metrics
- **WHEN** daily health metrics are saved and later loaded by user id and date
- **THEN** the loaded domain object contains the same supplied recovery values and source

#### Scenario: Enforcing activity ownership
- **WHEN** a repository operation loads or updates an activity by id for a different user
- **THEN** the system does not return or mutate that activity
