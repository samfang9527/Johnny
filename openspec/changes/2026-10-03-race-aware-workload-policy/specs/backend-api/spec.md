## MODIFIED Requirements

### Requirement: Race Goal API
Race create, update, and read contracts SHALL accept and return optional course ascent, descent, terrain difficulty, cutoff, and goal intent fields. Existing clients omitting them SHALL continue to work.

#### Scenario: Legacy race request
- **WHEN** a client sends only the existing required race fields
- **THEN** the request remains valid and omitted course fields are returned as null

### Requirement: Training Plan API
Generated plan responses SHALL expose the preparation assessment and its limitations without exposing private internal evidence or model prompts.

#### Scenario: Plan with preparation gap
- **WHEN** a generated Plan Version has a `gap` assessment
- **THEN** a plan read exposes the status, short athlete-facing explanation, and contributing factors
- **AND** existing workout and plan response fields retain their current meaning

#### Scenario: Legacy or manual plan
- **WHEN** a Plan Version predates this change or was manually created without policy metadata
- **THEN** the preparation assessment is absent or unknown without preventing the plan from loading
