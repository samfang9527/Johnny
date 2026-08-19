# Delta for Recommendation and Approval

## ADDED Requirements

### Requirement: Evidence-Backed Recommendation

The system SHALL store each training recommendation with structured evidence and a proposed action.

#### Scenario: Creating daily recommendation

- GIVEN Today context includes a planned workout and recovery evidence
- WHEN a recommendation is created
- THEN the system stores the recommendation summary, evidence values, proposed action, and status

### Requirement: User Decision

The system SHALL require user decision before applying significant training adjustments.

#### Scenario: Accepting a workout adjustment

- GIVEN a pending recommendation proposes a workout adjustment
- WHEN the user accepts it
- THEN the system marks the recommendation accepted and applies the approved adjustment

### Requirement: Decision History

The system SHALL preserve recommendation decision history.

#### Scenario: Rejecting a recommendation

- GIVEN a pending recommendation exists
- WHEN the user rejects it
- THEN the system records the rejection and leaves the original workout unchanged

