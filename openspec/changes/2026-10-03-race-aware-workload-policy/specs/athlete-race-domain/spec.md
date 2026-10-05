## MODIFIED Requirements

### Requirement: Race Strategy Details
The system SHALL allow a Race Goal to record optional course and goal context without changing existing required race fields.

#### Scenario: Creating a trail Race Goal
- **WHEN** an athlete saves a race with distance, date, ascent, descent, terrain difficulty, cutoff, and completion or performance intent
- **THEN** the system validates and persists these fields and returns them through race reads and planning context

#### Scenario: Reading an existing Race Goal
- **GIVEN** a Race Goal was saved before course fields existed
- **WHEN** it is read or selected for generation
- **THEN** its course fields are unknown and generation remains possible
- **AND** the system does not infer terrain or elevation from the race name

#### Scenario: Rejecting invalid course data
- **WHEN** ascent, descent, or cutoff is negative, or terrain or intent is unsupported
- **THEN** the request fails validation without modifying the Race Goal
