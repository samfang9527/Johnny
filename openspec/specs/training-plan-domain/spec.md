## Purpose
Define the training plan domain behavior for dated planned workouts, workout status lifecycle, adjustment proposals, and repository persistence mapping.

## Requirements

### Requirement: Training Plan Calendar
The system SHALL represent a user's training plan as dated planned workouts tied to a user and optional race goal, with lifecycle states for active, completed, archived, draft, and superseded plans.

#### Scenario: Creating a manual plan
- **GIVEN** a user has an athlete profile and optional race goal
- **WHEN** a training plan is created with start date, end date, and dated workouts
- **THEN** the system stores the plan and workouts in calendar order

#### Scenario: Creating an active generated race plan
- **GIVEN** a user has an athlete profile and a generated race plan
- **WHEN** the generated plan is stored
- **THEN** the system stores the plan with status `active`
- **AND** overlapping active plans for the same race are marked `superseded`

#### Scenario: Rejecting invalid plan date range
- **WHEN** a training plan is created with an end date before the start date
- **THEN** the system rejects the training plan with a validation error

#### Scenario: Rejecting workout outside plan boundaries
- **WHEN** a workout is scheduled before the plan start date or after the plan end date
- **THEN** the system rejects the training plan with a validation error

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

#### Scenario: Rejecting unsupported workout type
- **WHEN** a workout is created with an unsupported workout type
- **THEN** the system rejects the workout with a validation error

#### Scenario: Rejecting workout without planned load
- **WHEN** a workout is created without planned distance and without planned duration
- **THEN** the system rejects the workout with a validation error

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
The system SHALL persist training plan domain objects through repository methods using the existing persistence schema, including JSON-backed structured workout data and plan metadata.

#### Scenario: Loading persisted plan with workouts
- **WHEN** a training plan with workouts is saved and later loaded by user id
- **THEN** the loaded domain object contains the same plan dates, optional race id, ordered workouts, statuses, and planned workout details

#### Scenario: Persisting structured workout details
- **WHEN** a training plan with structured workout steps is saved and later loaded by user id
- **THEN** the loaded domain object contains the same step types, repeat counts, nested steps, target intent, target snapshots, phase, coach note, and planned load details

#### Scenario: Persisting plan version metadata
- **WHEN** a generated race plan version is saved and later loaded
- **THEN** the loaded plan contains `plan_series_id`, `previous_plan_id`, version, generation mode, continuity summary, and weekly rationales from plan metadata

#### Scenario: Loading legacy workout display steps
- **WHEN** a stored workout has no structured steps but has duration or distance details
- **THEN** repository reads expose a synthetic `free_run` step for display
- **AND** the stored workout JSON is not mutated by the read

#### Scenario: Loading persisted adjustment proposals
- **WHEN** an adjustment proposal is saved and later listed for a user-scoped plan
- **THEN** the loaded proposal contains the same before payload, after payload, status, and linked plan/workout identifiers

#### Scenario: Enforcing plan ownership
- **WHEN** a repository operation loads or updates a training plan by id for a different user
- **THEN** the system does not return or mutate that training plan

### Requirement: Generated Plan Activation Lifecycle
The system SHALL create generated training plans as active plans immediately.

#### Scenario: Creating generated plan for a race
- **GIVEN** an active plan already exists for a race
- **WHEN** a generated plan is created for the same race
- **THEN** the generated plan is stored as `active`
- **AND** the previous overlapping active plan for that race is marked `superseded`

#### Scenario: Preserve non-overlapping plan for same race
- **GIVEN** an active plan exists for the same race in a non-overlapping date range
- **WHEN** a generated plan is created for that race
- **THEN** the non-overlapping race plan remains `active`

#### Scenario: Creating base plan without race
- **GIVEN** a generated base plan has no race
- **WHEN** the generated plan is created
- **THEN** the base plan is stored as `active`

#### Scenario: Preserve other race plans
- **GIVEN** an active plan exists for a different race
- **WHEN** a generated plan is created for another race
- **THEN** the other race plan remains `active`
