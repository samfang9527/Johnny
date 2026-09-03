## MODIFIED Requirements

### Requirement: Training Plan API
The API SHALL expose training plans and workouts with structured details while preserving compatibility with existing simple workout fields.

#### Scenario: Creating a manual plan with structured workout steps
- **WHEN** a client posts a training plan whose workouts include structured steps, phase, and coach note
- **THEN** the API validates the payload through the same workout-detail contract used by generated plans
- **AND** stores the plan when the payload is valid

#### Scenario: Returning detailed workout responses
- **WHEN** a client lists or fetches training plans
- **THEN** each workout response includes existing simple fields
- **AND** includes structured steps, phase, coach note, and deterministic compact summary when available

#### Scenario: Returning plan metadata
- **WHEN** a client lists or fetches training plans
- **THEN** each training plan response includes plan version metadata when available

#### Scenario: Backward-compatible simple workouts
- **WHEN** a stored workout has no structured steps
- **THEN** the API still returns the existing purpose, distance, duration, pace range, heart-rate zone, and status fields
