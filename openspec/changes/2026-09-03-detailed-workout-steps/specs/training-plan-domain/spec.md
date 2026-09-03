## MODIFIED Requirements

### Requirement: Workout Details
The system SHALL represent planned workout details needed by Today, analytics, recommendation, and execution workflows, including structured workout steps for generated key workouts.

#### Scenario: Creating a planned run workout
- **WHEN** a workout is created with supported type, purpose, scheduled date, planned distance or duration, optional pace range, optional heart-rate zone, optional phase, optional coach note, and optional structured steps
- **THEN** the system stores the workout details as a valid planned workout

#### Scenario: Creating an interval workout with repeat steps
- **WHEN** a generated interval workout includes warmup, repeat block, recovery, and cooldown steps
- **THEN** the system validates each step type, nested repeat count, step target, distance or duration load, and total load consistency
- **AND** the workout can produce a deterministic compact summary from the steps

#### Scenario: Rejecting malformed workout steps
- **WHEN** a non-repeat workout step has neither distance nor duration
- **THEN** the system rejects the workout with a validation error

#### Scenario: Rejecting malformed repeat blocks
- **WHEN** a repeat block has no nested steps or a repeat count less than one
- **THEN** the system rejects the workout with a validation error

#### Scenario: Preserving coach note as non-canonical guidance
- **WHEN** a workout includes a coach note
- **THEN** the system stores the note only when it is within the configured length limit
- **AND** canonical workout summaries are still derived from structured steps, not from the coach note

### Requirement: Pace Profile
The system SHALL calculate workout target snapshots from a deterministic athlete pace profile rather than treating LLM-authored exact paces as authoritative.

#### Scenario: Threshold baseline supports pace ranges
- **GIVEN** an athlete profile contains a threshold pace baseline in training preferences
- **WHEN** the system builds the athlete pace profile
- **THEN** it creates high-confidence pace zones for `easy`, `steady`, `marathon`, `threshold`, `interval`, and `repetition`

#### Scenario: Race target supports only low-confidence fallback
- **GIVEN** no threshold pace baseline exists
- **AND** the selected race has a target finish time
- **WHEN** the system builds the athlete pace profile
- **THEN** it may derive low-confidence target guidance from race target pace
- **AND** low-confidence generated workout targets render as RPE-only

#### Scenario: Recent activity supports only low-confidence fallback
- **GIVEN** no threshold pace baseline exists
- **AND** recent activities include average pace data
- **WHEN** the system builds the athlete pace profile
- **THEN** it may derive low-confidence target guidance from selected key activities
- **AND** low-confidence generated workout targets render as RPE-only

### Requirement: Plan Continuity
The system SHALL preserve race-plan continuity across generated plan versions.

#### Scenario: Creating a continued race-plan version
- **GIVEN** an active race plan exists
- **WHEN** the user explicitly generates a rolling continuation
- **THEN** the generated plan records a stable plan series identifier, previous plan identifier, version metadata, continuity summary, and weekly rationales
- **AND** the prior plan remains available as history

#### Scenario: Preserving completed workout history
- **GIVEN** earlier workouts in the plan series are completed, skipped, or manually adjusted
- **WHEN** a new full projection is generated from today through race day
- **THEN** the generated plan does not replace those historical workout records
- **AND** future planned workouts use the latest active projection
