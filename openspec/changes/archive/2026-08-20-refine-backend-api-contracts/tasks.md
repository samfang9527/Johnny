## 1. API Versioning

- [x] 1.1 Add an API v1 router boundary in `create_app()` while leaving `/health` and `/ready` unversioned.
- [x] 1.2 Move product route groups from `/api/...` to `/api/v1/...` without changing route handler business behavior.
- [x] 1.3 Update API contract tests and helper URLs to use `/api/v1`.
- [x] 1.4 Verify unversioned `/health` and `/ready` still respond through the existing health routes.

## 2. Shared List Paging

- [x] 2.1 Add shared `PagingMeta` and `ListEnvelope` API schemas with `limit`, `offset`, and `has_next`.
- [x] 2.2 Add a helper for effective list paging defaults, validation, and limit-plus-one `has_next` calculation.
- [x] 2.3 Update race, training plan, activity, health, recommendation, and other list endpoints to return `ListEnvelope`.
- [x] 2.4 Update repository list calls or route-level query sizes so list endpoints fetch `limit + 1` rows and return only `limit` items.
- [x] 2.5 Add tests for `has_next=true`, `has_next=false`, default paging, and invalid paging validation.

## 3. Sync Connection Lifecycle

- [x] 3.1 Add repository methods to find connections by `(provider, provider_account_id)`, find active sync provider connections for a user, replace active connections, and reactivate an existing connection.
- [x] 3.2 Add repository behavior to reset or mark stale resource cursors when an existing connection is reactivated.
- [x] 3.3 Add an application use case for connecting a sync provider that enforces one active provider, global provider account ownership, and same-user reactivation.
- [x] 3.4 Update the integration connection API request validation to require `provider_account_id` for sync provider connections.
- [x] 3.5 Update `/api/v1/integrations/connections` to call the connection lifecycle use case instead of blindly creating a row.
- [x] 3.6 Preserve replaced connection rows and historical imported activity/health records linked to those rows.

## 4. Verification And Documentation

- [x] 4.1 Add tests for first connection, provider replacement, same-user reactivation, cross-user conflict, and cursor reset/stale behavior.
- [x] 4.2 Add or update tests proving historical activity/health rows remain linked to replaced provider connections.
- [x] 4.3 Update `docs/backend_api.md` with `/api/v1`, list envelope paging, and sync provider replacement/reactivation semantics.
- [x] 4.4 Run focused backend API and integration lifecycle tests.
- [x] 4.5 Run the full backend test suite.
- [x] 4.6 Run `openspec validate --changes "refine-backend-api-contracts"`.
