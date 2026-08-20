## 1. Integration Contracts

- [x] 1.1 Add integration domain/application value objects for provider fetch results, normalized payload results, sync summaries, outbox events, notification intents, and delivery attempts.
- [x] 1.2 Add application-facing protocols for provider adapters, integration stores, outbox stores, notification stores, and channel delivery gateways.
- [x] 1.3 Add unit tests for contract validation, credential-secret-reference handling, sync summary counts, and safe error summaries.

## 2. Persistence Adapters

- [x] 2.1 Implement integration repository methods for sync run creation, completion, failure, and resource cursor updates over existing tables.
- [x] 2.2 Implement outbox repository methods for creating `ActivityIngested` events and listing pending events with paging.
- [x] 2.3 Implement notification repository methods for intent creation, delivery attempt recording, delivered state, failed/retryable state, and paging.
- [x] 2.4 Add integration database tests for sync runs, cursor updates, outbox events, notification intents, delivery attempts, tenant scoping, and retry state.

## 3. Garmin-Compatible Normalization

- [x] 3.1 Add sample Garmin-compatible activity and daily health payload fixtures based on the existing probe expectations.
- [x] 3.2 Implement activity normalization into `CompletedActivity` with provider connection and source activity metadata.
- [x] 3.3 Implement health normalization into `DailyHealthMetrics`, preserving supported metrics and ignoring unsupported provider fields.
- [x] 3.4 Add normalization tests for supported activity fields, supported health metrics, missing optional fields, and invalid required fields.

## 4. Provider Ingestion Workflow

- [x] 4.1 Implement provider sync handler that creates a sync run, fetches provider payloads, normalizes records, and records summary counts.
- [x] 4.2 Add duplicate detection so repeated provider activity IDs for the same connection do not create duplicate activities.
- [x] 4.3 Emit `ActivityIngested` outbox events only for newly persisted provider activities.
- [x] 4.4 Add sync workflow tests for success, duplicate payloads, partial normalization failures, failed provider fetch, and cursor advancement rules.

## 5. Notification Intent Workflow

- [x] 5.1 Implement notification intent creation for recommendation notifications without calling channel adapters.
- [x] 5.2 Implement LINE notification payload formatting with concise message body and Johnny approval/evidence pointer.
- [x] 5.3 Add tests proving intent creation records user, recommendation, channel, schedule, payload, and does not deliver immediately.

## 6. LINE Delivery and Retry

- [x] 6.1 Implement fake LINE delivery gateway for success and failure responses.
- [x] 6.2 Implement notification delivery handler that records each attempt and updates intent status.
- [x] 6.3 Implement retry behavior that preserves the original intent and records a new delivery attempt.
- [x] 6.4 Add tests for successful delivery, failed delivery, retryable state, terminal failure policy, and duplicate-intent avoidance.

## 7. Verification

- [x] 7.1 Run focused integration normalization, ingestion, notification, and persistence tests.
- [x] 7.2 Run the full backend test suite.
- [x] 7.3 Update documentation if implementation changes schema interpretation, provider payload assumptions, or notification channel policy.
