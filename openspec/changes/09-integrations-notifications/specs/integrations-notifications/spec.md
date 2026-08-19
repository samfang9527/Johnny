# Delta for Integrations and Notifications

## ADDED Requirements

### Requirement: Activity Integration Boundary

The system SHALL normalize external activity data before storing it as activities.

#### Scenario: Provider activity received

- WHEN an activity payload is received from the MVP provider
- THEN the system normalizes it into the activity domain format
- AND duplicate provider activities are not stored twice

### Requirement: Ingestion Event

The system SHALL emit an activity ingested event after a new activity is stored.

#### Scenario: New activity stored

- WHEN a new provider activity is persisted
- THEN the system emits `ActivityIngested` for downstream analytics and recommendation workflows

### Requirement: Notification Intent Delivery

The system SHALL create notification intents separately from channel delivery.

#### Scenario: LINE notification requested

- GIVEN a recommendation should notify the user
- WHEN a notification intent is created
- THEN the LINE adapter attempts delivery and records the delivery result

