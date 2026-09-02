## MODIFIED Requirements

### Requirement: Evidence-Backed Recommendation
The system SHALL store each training recommendation with structured evidence, a proposed action, lifecycle status, and user ownership, including generated training plan approval recommendations.

#### Scenario: Creating daily recommendation
- **WHEN** a daily recommendation is created from Today context containing a planned workout and recovery evidence
- **THEN** the system stores title, rationale, recommendation type, priority, structured evidence values, proposed action, owner user, and `pending` status

#### Scenario: Creating training plan recommendation
- **WHEN** a training-plan generation workflow creates a draft plan
- **THEN** the system stores a `training_plan_creation` recommendation
- **AND** its proposed action references the draft training plan id and compact summary

#### Scenario: Reject malformed evidence
- **WHEN** a recommendation is created with evidence items missing required `source`, `metric`, or `value` fields
- **THEN** the system rejects the recommendation before persistence

#### Scenario: Informational recommendation
- **WHEN** a recommendation has proposed action type `no_plan_change`
- **THEN** the system stores it without requiring a training plan or workout reference

## ADDED Requirements

### Requirement: User Decision Required For Generated Training Plans
The system SHALL require an explicit user decision before activating generated draft training plans.

#### Scenario: Pending generated plan recommendation does not activate draft
- **WHEN** a pending recommendation proposes a `create_training_plan` action
- **THEN** the referenced draft plan remains `draft`
- **AND** no active plans are superseded

#### Scenario: Accepting generated plan recommendation
- **WHEN** the owner accepts a pending training-plan-creation recommendation
- **THEN** the system records decision `accepted`
- **AND** activates the referenced draft plan when ownership, freshness, and conflict checks pass
- **AND** supersedes conflicting active plans according to training-plan lifecycle rules

#### Scenario: Rejecting generated plan recommendation
- **WHEN** the owner rejects a pending training-plan-creation recommendation
- **THEN** the system records decision `rejected`
- **AND** leaves the draft plan inactive

#### Scenario: Blocking another user's generated plan recommendation
- **WHEN** a user attempts to accept another user's training-plan-creation recommendation
- **THEN** the system rejects the operation
- **AND** does not activate or supersede any plan
