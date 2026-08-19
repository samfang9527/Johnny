# Delta for Training Plan Domain

## ADDED Requirements

### Requirement: Training Plan Calendar

The system SHALL represent a training plan as dated planned workouts tied to a user and optional race.

#### Scenario: Creating a manual plan

- GIVEN a user has an athlete profile and race goal
- WHEN a training plan is created with dated workouts
- THEN the system stores the plan and workouts in calendar order

### Requirement: Workout Status Lifecycle

The system SHALL track workout status through planned, completed, skipped, and adjusted states.

#### Scenario: Skipping a workout

- GIVEN a planned workout exists
- WHEN the user marks it skipped
- THEN the system records the skipped status and preserves the original planned workout details

### Requirement: Plan Adjustment Proposal

The system SHALL represent proposed workout changes separately from applied changes.

#### Scenario: Proposing a shorter workout

- GIVEN a planned workout exists
- WHEN an adjustment is proposed
- THEN the system stores the before and after workout details without changing the workout until approved

