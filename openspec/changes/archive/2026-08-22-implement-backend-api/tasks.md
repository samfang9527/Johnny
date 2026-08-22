## 1. API Foundation

- [x] 1.1 Add API schema package for shared success envelopes, error envelopes, paging parameters, and common response models.
- [x] 1.2 Add FastAPI exception handlers for request validation errors, domain validation errors, not-found errors, and conflict errors.
- [x] 1.3 Add current-user dependency using the temporary local/test user boundary and document the `X-Johnny-User-Id` assumption in tests.
- [x] 1.4 Add dependency wiring for unit-of-work sessions, repository-backed stores, and application handlers without querying repositories directly in route handlers.
- [x] 1.5 Add API foundation tests for health preservation, current user context, structured errors, validation errors, and tenant-scope misses.

## 2. Athlete and Race API

- [x] 2.1 Add athlete profile request/response schemas and route tests for saving and loading the current user's profile.
- [x] 2.2 Implement athlete profile routes using the athlete profile store/application boundary.
- [x] 2.3 Add race goal request/response schemas and route tests for create, detail, update, and list with paging/date filters.
- [x] 2.4 Implement race goal routes with tenant-safe user scoping and structured not-found responses.

## 3. Training Plan and Workout API

- [x] 3.1 Add training plan and workout response schemas that include plan status, linked race, workouts, and workout details.
- [x] 3.2 Add route tests for creating/listing/loading training plans and hiding another user's plan.
- [x] 3.3 Implement training plan routes through the training plan application/store boundary.
- [x] 3.4 Add route tests and implementation for workout status/detail updates with domain validation handling.

## 4. Activity and Health API

- [x] 4.1 Add activity request/response schemas for manual activities and provider-backed activity metadata.
- [x] 4.2 Add route tests and implementation for creating manual activities and listing activities with paging/date filters.
- [x] 4.3 Add daily health metric response schemas grouped by metric date.
- [x] 4.4 Add route tests and implementation for reading daily health metrics by date range with paging.

## 5. Today Context API

- [x] 5.1 Add Today context response schema for next race, today's workout, recovery evidence, recent training context, and current recommendation.
- [x] 5.2 Add route tests for complete Today context aggregation and sparse-data success responses.
- [x] 5.3 Implement Today route using the existing training analytics and recommendation application boundaries.

## 6. Recommendation API

- [x] 6.1 Add recommendation list/detail/decision schemas, including evidence arrays and proposed action payloads for frontend rendering.
- [x] 6.2 Add route tests for listing recommendations and accepting, rejecting, and editing pending recommendations.
- [x] 6.3 Implement recommendation routes through the recommendation approval handlers.
- [x] 6.4 Add route tests and implementation for discussing a recommendation through the conversation/agent boundary when available.

## 7. Conversation API

- [x] 7.1 Add conversation message request/response schemas and validation for non-empty content.
- [x] 7.2 Add route tests for submitting a message and receiving a message or run reference.
- [x] 7.3 Implement conversation routes through a small application boundary that can later support asynchronous agent runs.

## 8. Integration Webhook API

- [x] 8.1 Add provider-neutral webhook request/response schemas for provider, connection id, payloads, and sync summary counts.
- [x] 8.2 Add route tests for successful provider payload ingestion, duplicate provider payloads, and unknown connection errors.
- [x] 8.3 Implement integration webhook routes through the provider ingestion handler without storing raw credentials.
- [x] 8.4 Add tests proving duplicate provider activity payloads return duplicate counts and do not emit another activity event.

## 9. Verification

- [x] 9.1 Run focused API contract tests for foundation, athlete/race, training plan/workout, activity/health, Today, recommendations, conversations, and integration webhooks.
- [x] 9.2 Run the full backend test suite.
- [x] 9.3 Update API documentation if route paths, current-user assumptions, error format, or response schemas differ from the design.
