## MODIFIED Requirements

### Requirement: Evidence-Backed Recommendation
The system SHALL store each training recommendation with structured evidence, a proposed action, lifecycle status, and user ownership. Generated training-plan activation is handled by the training-plan generation workflow, not recommendation approval.

#### Scenario: Informational recommendation
- **WHEN** a recommendation has proposed action type `no_plan_change`
- **THEN** the system stores it without requiring a training plan or workout reference

#### Scenario: Reject generated-plan activation recommendation
- **WHEN** a recommendation uses recommendation type `training_plan_creation` or proposed action type `create_training_plan`
- **THEN** the system rejects the recommendation before persistence

### Requirement: Plan Adjustment Application Safety
The system SHALL apply workout adjustments only when ownership and current workout state are valid.

#### Scenario: Block unsupported action application
- **WHEN** an accepted recommendation has proposed action type `no_plan_change`
- **THEN** the system records the decision without attempting a training-plan mutation
