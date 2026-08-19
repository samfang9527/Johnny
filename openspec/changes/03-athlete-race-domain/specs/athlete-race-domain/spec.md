# Delta for Athlete and Race Domain

## ADDED Requirements

### Requirement: Athlete Profile

The system SHALL represent a runner's baseline training context and preferences.

#### Scenario: Creating an athlete profile

- WHEN a user provides experience level, current weekly mileage, preferred training days, and maximum runs per week
- THEN the system stores a valid athlete profile for training decisions

### Requirement: Race Goal

The system SHALL represent a target race with date, distance, and optional target finish time.

#### Scenario: Creating a marathon goal

- GIVEN a user has an athlete profile
- WHEN they create a marathon race with a date and target finish time
- THEN the system stores the race goal and derives the target average pace

### Requirement: Domain Validation

The system SHALL reject athlete and race values that would make training planning invalid.

#### Scenario: Invalid race date

- WHEN a user creates a race with a date in the past
- THEN the system rejects the race goal with a validation error

