## Why

Johnny becomes more useful when workout and health data can arrive through provider syncs and important recommendations can proactively reach the user. This change adds the MVP integration and notification boundaries needed to ingest provider data, emit downstream events, and deliver notification intents without coupling agents directly to channels.

## What Changes

- Add provider integration contracts for external activity and health payload sync.
- Add normalization workflows that convert provider payloads into existing activity and health domain objects.
- Add sync-run and duplicate-detection behavior over the existing integration and activity persistence schema.
- Add `ActivityIngested` outbox events for newly stored provider activities.
- Add notification intent and delivery workflows separated from channel-specific adapters.
- Add a fake LINE delivery adapter and retry/failure state handling for MVP notification tests.
- Keep manual data input as a fallback and test fixture path.

## Capabilities

### New Capabilities

- `integrations-notifications`: Provider sync normalization, ingestion events, notification intent creation, LINE delivery boundary, and delivery retry/failure state tracking.

### Modified Capabilities

- None.

## Impact

- Adds application-layer integration and notification handlers, providers/gateways, domain value objects, and tests.
- Adds infrastructure repositories/adapters over existing `integration_connections`, `integration_resource_cursors`, `sync_runs`, `outbox_events`, `notification_intents`, and `notification_deliveries` tables.
- Uses existing activity/health persistence and training analytics/agent runtime downstream event boundaries.
- Does not store provider credentials directly; credential handling continues to use secret references or local token-store boundaries.
