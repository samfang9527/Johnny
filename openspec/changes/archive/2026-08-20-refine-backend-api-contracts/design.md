## Context

The backend API change added FastAPI route modules under `/api`, shared `DataEnvelope` and `ErrorEnvelope` schemas, repository-backed route handlers, and integration connection creation. Review feedback narrowed the next refinement to three contract decisions: product APIs should be versioned, list endpoints should expose a normalized MVP paging shape, and users should have only one active sync provider connection at a time.

The current integration schema already contains `IntegrationConnectionModel.status`, `credential_status`, `sync_status`, a global unique constraint for `(provider, provider_account_id)`, and provider connection foreign keys on imported activity data. This allows replacement/reactivation behavior to preserve provenance without hard deleting historical connection rows.

## Goals / Non-Goals

**Goals:**

- Expose all product API routes under `/api/v1` while keeping readiness and health checks unversioned.
- Normalize list responses with a shared `ListEnvelope` carrying `data` plus `paging.limit`, `paging.offset`, and `paging.has_next`.
- Compute `has_next` without count queries by fetching one extra row beyond the requested limit.
- Enforce one active sync provider connection per user.
- Preserve historical imported workout and health data when a user changes provider.
- Reuse a prior connection row when the same user reconnects the same `(provider, provider_account_id)`.
- Keep the global `(provider, provider_account_id)` uniqueness rule so one external provider account cannot be attached to multiple users.

**Non-Goals:**

- Do not add page numbers, total pages, or total record counts in MVP.
- Do not introduce cursor-based pagination in this change.
- Do not support multiple active sync providers for one user.
- Do not hard delete historical connection rows or imported workout/health records.
- Do not add production SSO or provider OAuth flows.

## Decisions

1. Add a versioned API router boundary in `create_app()`.

   `create_app()` should include product routes under one `/api/v1` prefix. Health and readiness routes remain at `/health` and `/ready` because they are operational checks, not product API contracts. Route modules can either keep workflow-local prefixes such as `/races` or be included through an API v1 aggregate router; the implementation should avoid repeating `/api/v1` across every module if a shared router keeps the code clearer.

   Alternative considered: keep `/api` until there is a public API. This makes early development slightly simpler, but it gives frontend and LLM clients a path shape that would immediately churn once versioning is introduced.

2. Use `ListEnvelope[T]` and `PagingMeta` for list endpoints.

   Keep `DataEnvelope[T]` for singleton/object commands and introduce a separate list envelope:

   - `data`: the returned items, capped to `limit`
   - `paging.limit`: effective limit used by the request
   - `paging.offset`: effective offset used by the request
   - `paging.has_next`: whether another request with `offset + limit` can fetch more data

   `has_next` should be computed by querying `limit + 1` rows, returning only the first `limit`, and setting `has_next` based on whether the extra row exists. This avoids expensive count queries and matches the MVP decision to only signal whether more data exists.

   Alternative considered: include `page_number`, `total_pages`, and `total_count`. That is convenient for table UIs but adds count query cost and can be misleading on mutable data. The MVP only needs to tell frontend or LLM callers whether they should continue fetching.

3. Treat connection creation as a sync-provider replacement use case.

   The API should no longer blindly create a connection row for every request. It should call an application-level use case that coordinates repository operations:

   - Require `provider_account_id` for sync provider connections.
   - Look up an existing connection by `(provider, provider_account_id)`.
   - If the existing connection belongs to another user, return a conflict.
   - If it belongs to the current user, reactivate that row, refresh credential metadata, and mark any other active sync provider connection for the user as `replaced`.
   - If no matching row exists, mark the current active sync provider connection for the user as `replaced` and create a new active row.

   Alternative considered: allow duplicates and dedupe activities later. That would make connection history harder to reason about and leaves duplicate provider accounts possible across users.

4. Preserve data provenance through connection status, not deletion.

   Replaced connections should remain in the database with `status = "replaced"` and `disconnected_at` set. Historical activities and health-derived records stay linked to their original provider connection. This keeps auditability and source provenance while still enforcing the business rule that only one provider actively syncs.

   Alternative considered: hard delete replaced connections. That saves a small amount of disk but either breaks foreign key provenance or forces imported records to lose the provider connection that produced them.

5. Reset resource cursors when reactivating an old connection.

   When a user switches away from a provider and later switches back to the same provider account, the old connection row should become active again. Its resource cursors should be reset or marked stale so the next sync can perform a safe lookback and rely on existing activity/health uniqueness to avoid duplicates. This prevents stale cursor state from skipping data created while the provider was inactive.

   Alternative considered: leave cursors unchanged. That is faster but risks missing provider data from the inactive period.

## Risks / Trade-offs

- Changing `/api` to `/api/v1` breaks existing local tests and any early clients -> Update tests, docs, and route registration in the same change.
- `has_next` can change between requests if new data arrives -> Accept this as normal offset pagination behavior for MVP.
- Requiring `provider_account_id` may reject provider integrations that cannot identify an account yet -> Keep the validation explicit because nullable values weaken the global uniqueness guarantee.
- Reactivating old rows can surprise observability unless status transitions are visible -> Preserve `connected_at`, update `disconnected_at`, credential metadata, and cursor state consistently.
- Resetting cursors can re-read older data -> Existing provider activity uniqueness and health metric idempotency should absorb duplicates during ingestion.

## Migration Plan

1. Add the shared API v1 router boundary and update route prefixes.
2. Add `PagingMeta`, `ListEnvelope`, and helper logic for limit-plus-one paging.
3. Update list routes and repository list calls to request one extra row and return normalized paging metadata.
4. Add repository/application behavior for finding existing provider accounts, replacing active connections, reactivating same-user connections, and resetting cursors.
5. Update contract tests, integration lifecycle tests, and backend API documentation.
6. Run OpenSpec validation and the backend test suite.

Rollback is straightforward for the API route and paging code by reverting the route registration and schema changes. Connection lifecycle changes should be rolled back only with a data review because `replaced` statuses may already exist after deployment.

## Open Questions

- None for MVP. The approved status vocabulary is `active`, `replaced`, and `disconnected`; future provider-specific lifecycle statuses can be added only when a real workflow requires them.
