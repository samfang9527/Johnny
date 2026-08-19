# Delta for Activity and Health Domain

## ADDED Requirements

### Requirement: Activity Recording

The system SHALL record completed running activities with normalized distance, duration, pace, heart rate, and source fields.

#### Scenario: Manual activity entry

- WHEN a user records a manual run with distance and duration
- THEN the system stores the activity and derives average pace

### Requirement: Health Metric Recording

The system SHALL record daily health metrics used for recovery context.

#### Scenario: Daily recovery entry

- WHEN a user records sleep duration, HRV, and resting heart rate for a date
- THEN the system stores one health metric record for that user and date

### Requirement: Workout Matching

The system SHALL allow an activity to be matched to a planned workout.

#### Scenario: Matching completed workout

- GIVEN a planned workout exists for a date
- WHEN a running activity is recorded for the same date
- THEN the system can link the activity to the planned workout

