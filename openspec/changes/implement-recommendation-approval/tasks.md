## 1. Recommendation Domain

- [x] 1.1 Add recommendation domain value objects for evidence items, proposed actions, recommendation lifecycle, priorities, statuses, and decisions.
- [x] 1.2 Add unit tests for valid recommendation creation, malformed evidence rejection, unsupported action rejection, and informational `no_plan_change` recommendations.
- [x] 1.3 Add unit tests and implementation for accepting, rejecting, and editing only pending recommendations.
- [x] 1.4 Add unit tests proving edits preserve original evidence/proposed action and create a revised pending recommendation payload.

## 2. Application Workflow

- [x] 2.1 Define application repository interfaces for user-scoped recommendation create/get/list/decision behavior and plan-adjustment reads/writes needed by approval services.
- [x] 2.2 Add service tests proving pending `adjust_workout` recommendations do not mutate workouts before acceptance.
- [x] 2.3 Implement recommendation decision service for accept, reject, edit, and `no_plan_change` decisions using trusted `user_id`.
- [x] 2.4 Add service tests proving accepted workout adjustments validate current `before_payload`, apply `after_payload`, and reject stale or cross-user attempts.
- [x] 2.5 Add deterministic daily recommendation service tests using fixture Today context for recovery warning and insufficient-context cases.
- [x] 2.6 Implement the daily recommendation service shell without LLM-generated text.

## 3. Persistence

- [x] 3.1 Extend SQLAlchemy recommendation repository to persist and load domain recommendation payloads with structured evidence/proposed action metadata.
- [x] 3.2 Add user-scoped recommendation history listing with `limit` and `offset` paging.
- [x] 3.3 Add persistence tests for recommendation history ownership, deterministic ordering, accepted/rejected/edited decisions, and preserved evidence/action JSON.
- [x] 3.4 Extend plan adjustment persistence behavior as needed for approval timestamps, applied status, and before/after payload history.
- [x] 3.5 Verify existing database metadata and migrations still match without adding a new migration.

## 4. Verification

- [x] 4.1 Run focused recommendation approval unit and integration tests.
- [x] 4.2 Run the full backend test suite.
- [x] 4.3 Run `openspec validate implement-recommendation-approval`.
