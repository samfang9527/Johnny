## MODIFIED Requirements

### Requirement: Race Goal Entry
The Race Goal form SHALL offer optional structured course and goal fields with clear units and allow an athlete to leave them unknown.

#### Scenario: Entering a trail race
- **WHEN** the athlete enters a 40 km trail Race Goal and known ascent or cutoff
- **THEN** the form sends those values in the race request and displays them when the Race Goal is read

### Requirement: Plan Assessment Display
The Plan view SHALL display a generated Plan Version's preparation assessment near its Race Strategy and explain a material gap or unknown input in Traditional Chinese.

#### Scenario: Material preparation gap
- **WHEN** the Active Projection has a `gap` assessment
- **THEN** the athlete can see the contributing factors without opening individual workouts
- **AND** the copy does not promise race completion or imply medical clearance

#### Scenario: Legacy plan
- **WHEN** the Active Projection has no assessment
- **THEN** the Plan view remains usable and does not display a fabricated readiness claim
