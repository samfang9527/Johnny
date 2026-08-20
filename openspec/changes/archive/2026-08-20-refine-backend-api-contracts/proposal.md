## Why

The MVP backend API exists, but several contract details should be stabilized before frontend and LLM clients depend on it. This change refines route versioning, list response paging, and sync provider connection lifecycle so later implementation does not require disruptive API or database migrations.

## What Changes

- **BREAKING**: Move product API routes from `/api/...` to `/api/v1/...`, while keeping `/health` and `/ready` unversioned.
- Add a shared list response envelope with `data` and `paging`, where `paging` includes `limit`, `offset`, and `has_next`.
- Keep MVP list paging lightweight by using `has_next` only; do not add total count, page number, or total pages queries.
- Enforce one active sync provider connection per user at a time.
- Preserve historical imported activity and health data by marking replaced connections as `replaced` rather than deleting connection rows.
- Keep a global unique constraint for `(provider, provider_account_id)` and reactivate the existing connection row when the same user reconnects the same provider account.
- Reject reconnect attempts when `(provider, provider_account_id)` already belongs to a different user.

## Capabilities

### New Capabilities

- `backend-api-contract-refinements`: Versioned API route contracts and shared MVP list paging response behavior.
- `sync-connection-lifecycle`: Single-active-provider connection replacement, reactivation, and cross-user account conflict behavior.

### Modified Capabilities

- None.

## Impact

- Affects FastAPI router registration, API schema modules, route tests, and backend API documentation.
- Affects integration connection application logic, repository behavior, tests, and any migration needed to support replacement/reactivation safely.
- Does not add production SSO, cursor-based pagination, total-count pagination, multi-provider sync, or hard deletion of historical provider connection records.
