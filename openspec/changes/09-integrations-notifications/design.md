# Design: Integrations and Notifications

## Design Status

Discussion required before implementation.

## Approach

Keep provider-specific logic in infrastructure adapters. Domain and application services should only see normalized activity and health data.

Integration structure:

- Provider connection record
- Sync run record
- Provider adapter
- Normalizer
- Ingestion service
- Outbox event

Notification structure:

- Notification intent
- Channel policy
- LINE adapter
- Delivery record
- Retry handling

## Design Decisions

- Choose one primary activity provider for MVP.
- Keep manual data entry as fallback and test fixture source.
- Use notification intents so the agent never sends channel messages directly.
- Send concise LINE messages that link or point back to Johnny for evidence and approval.

## Testing Strategy

- Adapter tests with sample provider payloads.
- Normalization tests.
- Duplicate detection tests.
- Event emission tests.
- Fake LINE adapter delivery tests.
- Failure and retry state tests.

## Risks

- Provider API access may delay implementation. Manual entry and adapter interfaces reduce blocking.
- Notifications can become noisy. MVP should limit notification types.

