# Feature 09: Integrations and Notifications

## Order

9 of 12. This follows agent and recommendation foundations and precedes API/frontend completion.

## Layer

Infrastructure adapters and async business workflows.

## Goal

Connect MVP data ingestion and notification delivery without coupling domain logic to external providers.

## Depends On

- `01-project-foundation`
- `02-persistence-schema`
- `05-activity-health-domain`
- `06-training-analytics`
- `07-recommendation-approval`
- `08-agent-runtime-tools`

## Delivers

- One primary activity integration path, preferably Strava first unless Garmin access is ready
- Manual ingestion remains available
- Integration connection records
- Sync run records
- Activity ingestion event
- Notification intent workflow
- LINE notification adapter

## Non-Goals

- No Apple Health
- No social/content ingestion
- No full Garmin and Strava parity in the same first slice unless explicitly approved
- No frontend integration settings UI

## Design Discussion Required

Before implementation, discuss `design.md` and confirm:

- Strava-first or Garmin-first MVP
- Webhook versus scheduled sync priority
- LINE notification message scope
- Retry and failure policy

## Testable Outcome

Adapter tests normalize provider activity payloads, ingestion tests emit events, and notification tests send through a fake LINE adapter while preserving delivery records.

