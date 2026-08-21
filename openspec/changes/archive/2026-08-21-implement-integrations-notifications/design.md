## Context

Johnny already has normalized activity and health domain models, Garmin schema probing work, application-facing stores/providers, agent runtime tools, and persistence tables for integration connections, resource cursors, sync runs, outbox events, notification intents, and notification deliveries. What is missing is the application workflow that turns external provider payloads into domain records, emits ingestion events, and sends proactive notifications through channel adapters.

The MVP provider should be Garmin-compatible because the project has already explored `garminconnect` payloads. Credentials must not be stored directly in the database; integration connection records should store provider identity, status, capabilities, metadata, and a secret/token reference only.

## Goals / Non-Goals

**Goals:**

- Add provider adapter contracts for fetching provider activity and health payloads.
- Add Garmin-compatible normalization from provider payloads to existing `CompletedActivity` and `DailyHealthMetrics` domain objects.
- Add ingestion handlers that deduplicate provider activities, persist new normalized records, update sync cursors/runs, and emit `ActivityIngested` events.
- Add notification intent creation separate from channel delivery.
- Add a LINE delivery gateway boundary with fake adapter tests for success, failure, and retry state.
- Keep manual activity/health input as a fallback path and test fixture source.

**Non-Goals:**

- No real LINE API credential wiring.
- No direct agent-to-channel messaging.
- No direct storage of Garmin usernames, passwords, or raw credentials in the database.
- No frontend notification settings UI.
- No broad multi-provider framework beyond interfaces and Garmin-compatible MVP payloads.

## Decisions

### Use Provider Adapters Plus Normalizers

Provider adapters fetch raw provider payloads and return provider-neutral fetch results. Normalizers convert each payload into activity and health domain objects before persistence. The ingestion handler only sees normalized domain objects plus provider identity metadata.

Alternative considered: persist raw provider payloads first and normalize later. That would make the MVP harder to reason about and risks letting provider-specific fields leak into application logic.

### Use Garmin-Compatible Payloads For MVP

The MVP provider shape should match the `garminconnect` data already probed in the project. The adapter boundary should still be provider-neutral enough to add other sources later.

Alternative considered: start with a generic manual-only adapter. That would not validate the real automatic-data path this change is meant to unlock.

### Deduplicate At The Provider Identifier Boundary

Provider activities should be deduplicated by provider connection and provider activity ID before inserting new `activities` rows. Duplicate payloads should be counted in sync summaries but must not emit duplicate downstream events.

Alternative considered: deduplicate by timestamp and distance. That is too fragile for edited or repeated workouts.

### Emit Outbox Events After New Activity Persistence

When a new provider activity is stored, the handler should write an `ActivityIngested` outbox event with user, activity, provider, and sync metadata. Downstream analytics or agent workflows can consume events later without the ingestion handler directly invoking them.

Alternative considered: call analytics or agent handlers inline. That couples provider sync latency and failures to downstream workflows.

### Separate Notification Intent From Delivery

Application code creates notification intents; channel delivery workers/adapters attempt delivery and record delivery rows. Agents and recommendation workflows should never call LINE directly.

Alternative considered: send LINE messages from recommendation or agent handlers. That would bypass retry state, delivery audit, and channel policy.

### Fake LINE Gateway First

Define a LINE delivery gateway and fake adapter for tests. Real LINE credentials and HTTP behavior can be added behind the same boundary in a later configuration-focused change.

Alternative considered: wire real LINE delivery immediately. That creates network and credential dependencies before the notification workflow is stable.

## Risks / Trade-offs

- Provider payload drift -> Keep sample payload fixtures and normalization contract tests close to adapter code.
- Garmin rate limiting or token expiry -> Sync handlers should record failed sync runs and avoid deleting existing cursors on failure.
- Duplicate events -> Deduplicate before activity insert and only emit outbox events for newly persisted records.
- Notification noise -> MVP should limit notification intent types and make channel policy explicit.
- Channel delivery failures -> Record failed deliveries with provider response details and keep intent state retryable.
- Sensitive payload leakage -> Store normalized summaries and provider IDs; avoid persisting credentials or broad raw payloads.

## Migration Plan

1. Add integration and notification domain/application value objects and protocols.
2. Implement repositories over existing sync, outbox, notification intent, and delivery tables.
3. Implement Garmin-compatible normalizers and ingestion handlers with duplicate detection.
4. Implement notification intent creation and fake LINE delivery workflow with retry/failure tests.
5. Update documentation only if implementation changes schema interpretation or channel policy.

Rollback is straightforward because the change uses existing schema and adds application code. Disabling scheduled sync and notification workers stops side effects while preserving historical sync and delivery records.

## Open Questions

- Which real LINE account and message template policy should be configured first?
- Should Garmin health sync run on the same cadence as activity sync or a separate schedule?
- How long should failed notification intents remain retryable before becoming terminal?
