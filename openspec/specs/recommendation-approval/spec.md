## Purpose
Define recommendation approval behavior for Johnny so training recommendations can be reviewed, discussed, accepted, rejected, or edited with explicit user control and durable history.

## Requirements

### Requirement: Evidence-Backed Recommendation
The system SHALL store each training recommendation with structured evidence, a proposed action, lifecycle status, and user ownership. Generated training-plan activation is handled by the training-plan generation workflow, not recommendation approval.

#### Scenario: Creating daily recommendation
- **WHEN** a daily recommendation is created from Today context containing a planned workout and recovery evidence
- **THEN** the system stores title, rationale, recommendation type, priority, structured evidence values, proposed action, owner user, and `pending` status

#### Scenario: Reject malformed evidence
- **WHEN** a recommendation is created with evidence items missing required `source`, `metric`, or `value` fields
- **THEN** the system rejects the recommendation before persistence

#### Scenario: Informational recommendation
- **WHEN** a recommendation has proposed action type `no_plan_change`
- **THEN** the system stores it without requiring a training plan or workout reference

#### Scenario: Reject generated-plan activation recommendation
- **WHEN** a recommendation uses recommendation type `training_plan_creation` or proposed action type `create_training_plan`
- **THEN** the system rejects the recommendation before persistence

### Requirement: User Decision Required For Significant Adjustments
The system SHALL require an explicit user decision before applying significant workout adjustments to a training plan.

#### Scenario: Pending recommendation does not mutate workout
- **WHEN** a pending recommendation proposes an `adjust_workout` action
- **THEN** the referenced workout remains unchanged until the user accepts the recommendation

#### Scenario: Accepting a workout adjustment
- **WHEN** the owner accepts a pending workout-adjustment recommendation
- **THEN** the system records decision `accepted`, marks the recommendation `decided`, approves and applies the linked adjustment, and updates the workout to the approved `after_payload`

#### Scenario: Rejecting a workout adjustment
- **WHEN** the owner rejects a pending workout-adjustment recommendation
- **THEN** the system records decision `rejected`, marks the recommendation `decided`, and leaves the original workout unchanged

### Requirement: Edit Workflow Preserves History
The system SHALL preserve original recommendation history when a user edits a proposed adjustment.

#### Scenario: Editing creates revised recommendation
- **WHEN** the owner edits a pending workout-adjustment recommendation
- **THEN** the original recommendation records decision `edited` and a new pending recommendation is created with the revised proposed action

#### Scenario: Original proposed action is preserved
- **WHEN** a recommendation is edited
- **THEN** the original recommendation keeps its original evidence and proposed action for audit history

### Requirement: Plan Adjustment Application Safety
The system SHALL apply workout adjustments only when ownership and current workout state are valid.

#### Scenario: Block stale adjustment
- **WHEN** an accepted recommendation's `before_payload` no longer matches the current workout payload
- **THEN** the system does not apply the adjustment and leaves the workout unchanged

#### Scenario: Block other user's recommendation
- **WHEN** a user attempts to decide or apply another user's recommendation
- **THEN** the system rejects the operation and does not mutate recommendation or workout state

#### Scenario: Block unsupported action application
- **WHEN** an accepted recommendation has proposed action type `no_plan_change`
- **THEN** the system records the decision without attempting a training-plan mutation

### Requirement: Decision History Retrieval
The system SHALL allow recommendation history to be retrieved for a user with paging.

#### Scenario: List recommendation history
- **WHEN** recommendation history is listed for a user with limit and offset
- **THEN** the system returns only that user's recommendations in deterministic order according to the requested page

#### Scenario: Exclude other user's history
- **WHEN** recommendation history is listed for a user
- **THEN** recommendations owned by other users are not returned

### Requirement: Deterministic Daily Recommendation Service
The system SHALL provide a daily recommendation service shell that can create recommendations from deterministic Today context without LLM-generated text.

#### Scenario: Recovery warning from Today context
- **WHEN** Today context indicates a planned workout and conservative recovery label `rest`
- **THEN** the service creates a pending workout-adjustment or recovery-warning recommendation with structured evidence from the Today context

#### Scenario: No recommendation when context is insufficient
- **WHEN** Today context lacks actionable plan or recovery evidence
- **THEN** the system does not create a plan-changing recommendation
