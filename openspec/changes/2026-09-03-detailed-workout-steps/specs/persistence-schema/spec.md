## MODIFIED Requirements

### Requirement: Training Plan Persistence Mapping
The system SHALL persist training plan domain objects through repository methods using JSON-backed details for structured workout data and plan metadata.

#### Scenario: Persisting structured workout details
- **WHEN** a training plan with structured workout steps is saved and later loaded by user id
- **THEN** the loaded domain object contains the same step types, repeat counts, nested steps, target intent, target snapshots, phase, coach note, and planned load details

#### Scenario: Persisting plan version metadata
- **WHEN** a generated race plan version is saved and later loaded
- **THEN** the loaded plan contains `plan_series_id`, `previous_plan_id`, version, generation mode, continuity summary, and weekly rationales from plan metadata

### Requirement: PostgreSQL Schema
The system SHALL provide database columns needed for V1 detailed workout steps without normalizing workout steps into a separate table.

#### Scenario: Adding plan metadata JSON
- **WHEN** migrations are applied
- **THEN** `training_plans` contains non-null JSON metadata with an empty object default

#### Scenario: Keeping workout steps in details JSON
- **WHEN** structured steps are persisted
- **THEN** they are stored in the existing `workouts.details` JSON column
- **AND** no `workout_steps` table is required in V1
