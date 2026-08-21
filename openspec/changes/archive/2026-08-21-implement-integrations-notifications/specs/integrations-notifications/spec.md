## ADDED Requirements

### Requirement: Provider Integration Boundary
The system SHALL fetch external activity and health data through provider adapter interfaces and SHALL expose only normalized domain objects to application workflows.

#### Scenario: Garmin-compatible activity payload received
- **WHEN** a Garmin-compatible activity payload is fetched
- **THEN** the system normalizes it into a `CompletedActivity`
- **AND** provider-specific identity is preserved as provider connection and source activity metadata
- **AND** raw credentials are not stored in the database

#### Scenario: Garmin-compatible health payload received
- **WHEN** a Garmin-compatible daily health payload is fetched
- **THEN** the system normalizes supported metrics into `DailyHealthMetrics`
- **AND** unsupported provider fields do not block supported metric persistence

### Requirement: Provider Activity Deduplication
The system SHALL avoid storing duplicate provider activities for the same integration connection and provider activity identifier.

#### Scenario: Duplicate provider activity received
- **GIVEN** an activity with the same provider connection and provider activity ID has already been persisted
- **WHEN** the same provider activity is ingested again
- **THEN** the system does not create another activity row
- **AND** it does not emit a duplicate `ActivityIngested` event
- **AND** the sync summary records the duplicate count

### Requirement: Sync Run Tracking
The system SHALL record provider sync attempts with status, timing, summary counts, and error information when available.

#### Scenario: Provider sync completes
- **WHEN** a provider sync completes successfully
- **THEN** the system marks the sync run as completed
- **AND** it records counts for fetched, stored, duplicate, and failed records
- **AND** it advances the relevant resource cursor

#### Scenario: Provider sync fails
- **WHEN** fetching or normalizing provider payloads fails
- **THEN** the system marks the sync run as failed
- **AND** it records a safe error summary
- **AND** it does not advance the successful sync cursor

### Requirement: Activity Ingestion Event
The system SHALL emit an `ActivityIngested` outbox event after a new provider activity is stored.

#### Scenario: New provider activity stored
- **WHEN** a normalized provider activity is persisted for the first time
- **THEN** the system creates an `ActivityIngested` outbox event
- **AND** the event payload includes user ID, activity ID, provider, integration connection ID, and sync run ID when available

### Requirement: Notification Intent Boundary
The system SHALL create notification intents separately from channel delivery.

#### Scenario: Recommendation notification requested
- **GIVEN** a recommendation should notify the user
- **WHEN** a notification intent is created
- **THEN** the intent records user ID, recommendation ID, channel, schedule time, and message payload
- **AND** no channel adapter is called during intent creation

### Requirement: LINE Delivery Boundary
The system SHALL deliver LINE notifications through a channel gateway and record each delivery attempt.

#### Scenario: LINE delivery succeeds
- **GIVEN** a pending LINE notification intent
- **WHEN** the LINE gateway accepts the message
- **THEN** the system records a successful delivery
- **AND** the notification intent is marked delivered

#### Scenario: LINE delivery fails
- **GIVEN** a pending LINE notification intent
- **WHEN** the LINE gateway rejects or fails the message
- **THEN** the system records a failed delivery with a safe provider response summary
- **AND** the notification intent remains retryable unless retry policy marks it terminal

### Requirement: Notification Retry State
The system SHALL support retrying failed notification deliveries without creating duplicate intents.

#### Scenario: Failed intent retried
- **GIVEN** a notification intent has a failed delivery attempt
- **WHEN** the delivery worker retries the intent
- **THEN** it records a new delivery attempt
- **AND** it preserves the original notification intent ID
