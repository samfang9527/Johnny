## Purpose
Define deterministic training analytics for Johnny so Today and recommendation features can rely on auditable, tenant-scoped metrics instead of LLM arithmetic.

## Requirements

### Requirement: Deterministic Training Load Metrics
The system SHALL calculate training load metrics with deterministic code from stored completed activities for a trusted user and anchor date.

#### Scenario: Weekly distance calculation
- **WHEN** training load metrics are calculated for a user with running activities in the seven-day window ending on the anchor date
- **THEN** the system returns weekly distance from those stored activities only

#### Scenario: Previous weekly distance calculation
- **WHEN** training load metrics are calculated for a user with running activities in the previous seven-day window
- **THEN** the system returns previous weekly distance from the immediately preceding seven-day window

#### Scenario: Mileage ramp percentage calculation
- **WHEN** current weekly distance and previous weekly distance are both available and previous weekly distance is greater than zero
- **THEN** the system returns mileage ramp percentage as the current weekly distance change relative to the previous weekly distance

#### Scenario: Unavailable mileage ramp
- **WHEN** previous weekly distance is zero or unavailable
- **THEN** the system marks mileage ramp percentage as unavailable instead of inventing a numeric value

### Requirement: Acute And Chronic Load Metrics
The system SHALL calculate acute load, chronic load, and acute-to-chronic ratio from normalized completed activity data.

#### Scenario: Acute load calculation
- **WHEN** acute load is calculated for an anchor date
- **THEN** the system returns the sum of activity load from the seven-day window ending on the anchor date

#### Scenario: Chronic load calculation
- **WHEN** chronic load is calculated for an anchor date
- **THEN** the system returns the average weekly activity load over the twenty-eight-day window ending on the anchor date

#### Scenario: Acute chronic ratio calculation
- **WHEN** acute load and chronic weekly load are both available and chronic weekly load is greater than zero
- **THEN** the system returns the acute-to-chronic load ratio

#### Scenario: Unavailable acute chronic ratio
- **WHEN** chronic weekly load is zero or unavailable
- **THEN** the system marks acute-to-chronic load ratio as unavailable instead of dividing by zero

### Requirement: Recovery Context
The system SHALL derive recovery context from available daily health metrics and recent training load without relying on LLM reasoning.

#### Scenario: Recovery signal deltas
- **WHEN** daily health metrics include HRV, HRV baseline, resting heart rate, and enough prior health metrics to derive resting heart rate baseline evidence
- **THEN** the system returns HRV delta and resting heart rate delta values as explicit recovery evidence

#### Scenario: Sleep debt calculation
- **WHEN** daily health metrics include sleep duration
- **THEN** the system returns sleep debt as the difference between expected sleep and actual sleep duration

#### Scenario: Conservative low recovery label
- **WHEN** sleep is below target, HRV is below baseline, resting heart rate is above baseline, or recent load has increased sharply
- **THEN** the system returns `caution` or `rest` according to the documented MVP thresholds with the evidence values that caused it

#### Scenario: Optional Body Battery evidence
- **WHEN** daily health metrics include Body Battery for the anchor date
- **THEN** the system includes Body Battery as explicit recovery evidence
- **AND** Body Battery scores of 25 or lower are `rest`, scores up to 50 are `caution`, and higher scores are `ready`
- **AND** the system still derives recovery context when Body Battery is absent

#### Scenario: Unknown recovery label
- **WHEN** required recovery inputs are missing
- **THEN** the system returns an `unknown` readiness label and lists unavailable signals without scoring them as zero

### Requirement: Today Context Aggregation
The system SHALL aggregate a structured Today context for a user and anchor date from training plan, activity, health, and analytics inputs.

#### Scenario: Today context includes planned workout
- **WHEN** a user has an active training plan with a workout scheduled for the anchor date
- **THEN** the Today context includes the scheduled workout payload and current workout status

#### Scenario: Today context includes recent evidence
- **WHEN** a user has recent completed activities and daily health metrics
- **THEN** the Today context includes recent activity summaries, training load metrics, recovery context, and source evidence values

#### Scenario: Today context excludes prose recommendations
- **WHEN** Today context is generated
- **THEN** the system returns structured data and does not generate coaching prose or final recommendations

### Requirement: Analytics Snapshot Persistence
The system SHALL persist and retrieve training metric snapshots for auditability and fast reuse.

#### Scenario: Persist training snapshot
- **WHEN** analytics are calculated for a user, snapshot type, and captured timestamp
- **THEN** the system stores a user-scoped training metric snapshot containing the computed metrics JSON

#### Scenario: Retrieve user snapshot
- **WHEN** a training metric snapshot is requested by user and snapshot identifier
- **THEN** the system returns the snapshot only if it belongs to that user

#### Scenario: Snapshot metric names remain explicit
- **WHEN** a snapshot is persisted
- **THEN** the metrics payload includes explicit keys for calculated values and unavailable signals

### Requirement: Missing Data Handling
The system SHALL mark unavailable inputs explicitly instead of inventing values for analytics calculations.

#### Scenario: Missing HRV
- **WHEN** no HRV value exists for the anchor date
- **THEN** the system marks HRV as unavailable and does not include it in numeric recovery scoring

#### Scenario: Missing activities
- **WHEN** no completed activities exist in a requested training-load window
- **THEN** the system returns zero totals where a real zero is meaningful and marks ratio metrics as unavailable when their denominator is unavailable or zero

### Requirement: Tenant-Scoped Analytics
The system SHALL include only data owned by the trusted user in analytics reads, calculations, and snapshot writes.

#### Scenario: Exclude other users activities
- **WHEN** training analytics are calculated for a user
- **THEN** completed activities belonging to other users are excluded from every metric

#### Scenario: Exclude other users snapshots
- **WHEN** snapshots are listed or loaded for a user
- **THEN** snapshots belonging to other users are not returned
