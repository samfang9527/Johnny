# Delta for Persistence Schema

## ADDED Requirements

### Requirement: Core Entity Persistence

The system SHALL persist MVP entities needed for the training recommendation loop.

#### Scenario: Creating core records

- GIVEN the database schema has been migrated
- WHEN records for user, athlete profile, race, training plan, workout, activity, health metric, recommendation, and agent run are created
- THEN each record is stored with a stable identifier and timestamps

### Requirement: Repository Boundary

The system SHALL access persisted MVP entities through repository interfaces rather than direct database access from application services.

#### Scenario: Loading a training plan

- GIVEN a training plan exists for a user
- WHEN an application service requests the current plan through a repository
- THEN the repository returns the plan and its workouts without exposing database session details

### Requirement: Audit-Oriented Records

The system SHALL preserve status and history fields for recommendations, plan adjustments, events, and agent runs.

#### Scenario: Recommendation decision recorded

- GIVEN a recommendation exists
- WHEN the user accepts, rejects, or edits it
- THEN the decision state and decision timestamp are persisted

