# Delta for Frontend Today and Calendar

## ADDED Requirements

### Requirement: Today Surface

The system SHALL show the user's next race, today's workout, recovery evidence, and current recommendation on the main page.

#### Scenario: User opens Today

- GIVEN Today context is available from the API
- WHEN the user opens the app
- THEN they see race countdown, workout details, recovery signals, recommendation summary, and evidence

### Requirement: Recommendation Actions

The system SHALL let users accept, reject, edit, or discuss a recommendation from the Today surface.

#### Scenario: Accept recommendation

- GIVEN a pending recommendation is shown
- WHEN the user accepts it
- THEN the frontend calls the recommendation accept API and updates the displayed status

### Requirement: Training Calendar

The system SHALL display planned workouts in a calendar-oriented view.

#### Scenario: Viewing upcoming workouts

- GIVEN the API returns planned workouts
- WHEN the user opens the calendar view
- THEN workouts are grouped by date with type, distance or duration, and status

