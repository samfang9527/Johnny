# Delta for Backend API

## ADDED Requirements

### Requirement: MVP Product Routes

The system SHALL expose API routes for athlete profile, race goals, training plans, workouts, activities, health metrics, Today context, recommendations, and conversations.

#### Scenario: Loading Today context

- GIVEN a user has a profile, race, training plan, workout, activity data, and analytics
- WHEN the frontend requests Today context
- THEN the API returns the next race, today's workout, recovery evidence, and current recommendation

### Requirement: Recommendation Decisions

The system SHALL expose API routes for accepting, rejecting, editing, and discussing recommendations.

#### Scenario: Accepting recommendation by API

- GIVEN a pending recommendation exists
- WHEN the frontend sends an accept request
- THEN the API applies the approved action and returns the updated recommendation state

### Requirement: API Validation

The system SHALL return structured validation errors for invalid requests.

#### Scenario: Invalid race request

- WHEN a request creates a race without a date
- THEN the API rejects it with a structured validation error

