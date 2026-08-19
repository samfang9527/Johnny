# Delta for Training Analytics

## ADDED Requirements

### Requirement: Deterministic Training Metrics

The system SHALL calculate core training metrics using deterministic code rather than LLM reasoning.

#### Scenario: Weekly distance calculation

- GIVEN a user has running activities in the last seven days
- WHEN training metrics are calculated for today
- THEN the system returns weekly distance and previous weekly distance from stored activity data

### Requirement: Recovery Context

The system SHALL derive recovery context from sleep, HRV, resting heart rate, and recent load where data is available.

#### Scenario: Low recovery signals

- GIVEN sleep is below baseline, HRV is below baseline, and recent load increased
- WHEN recovery context is calculated
- THEN the system returns a lower readiness label with evidence values

### Requirement: Missing Data Handling

The system SHALL mark unavailable signals explicitly instead of inventing values.

#### Scenario: Missing HRV

- GIVEN no HRV value exists for the date
- WHEN recovery context is calculated
- THEN the system marks HRV as unavailable and does not include it in numeric scoring

