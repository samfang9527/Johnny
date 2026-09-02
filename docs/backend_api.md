# Backend API

The MVP backend API is served by `src.main:create_app()`. Health checks remain at the root, while product routes use the `/api/v1` prefix.

## Local Current User

Until production authentication is implemented, API routes resolve the current user from local/test headers:

- `X-Johnny-User-Id`
- `X-Johnny-User-Email`
- `X-Johnny-User-Display-Name`

Write routes so the user id comes from this dependency, not from request bodies. Production SSO can replace this dependency later without changing route handlers.

## Error Format

Validation, not-found, conflict, and domain validation errors use this envelope:

```json
{
  "error": {
    "code": "validation_error",
    "message": "Request validation failed",
    "details": []
  }
}
```

Successful singleton and command responses use:

```json
{
  "data": {}
}
```

List responses use a shared paging envelope:

```json
{
  "data": [],
  "paging": {
    "limit": 20,
    "offset": 0,
    "has_next": false
  }
}
```

MVP paging intentionally exposes only `has_next`; it does not include `page_number`, `total_pages`, or `total_count`.

## Sync Provider Connections

Users can have only one active sync provider connection at a time. `POST /api/v1/integrations/connections` requires `provider_account_id` and applies these rules:

- Connecting the first provider account creates an `active` connection.
- Connecting a different provider account marks the previous active connection as `replaced` and creates a new `active` connection.
- Connecting the same `(provider, provider_account_id)` again for the same user reactivates the existing row instead of creating a duplicate.
- Connecting a provider account that belongs to another user returns a conflict error.
- Replaced connection rows and imported activity/health records are preserved so historical data keeps provider provenance.
- `DELETE /api/v1/integrations/connections/{connection_id}` disconnects a Garmin connection, deletes its encrypted credential row, and preserves imported activity/health records.
- `POST /api/v1/integrations/connections/{connection_id}/admin-token-import` is backend-only and requires `X-Johnny-Admin-Token` matching `JOHNNY_ADMIN_TOKEN`; it stores an encrypted Garmin session payload without returning the raw payload.

## Route Groups

- `GET /health`
- `GET /ready`
- `GET /api/v1/me`
- `GET|PUT /api/v1/athlete/profile`
- `GET|POST /api/v1/races`
- `GET|PUT /api/v1/races/{race_id}`
- `GET|POST /api/v1/training-plans`
- `GET /api/v1/training-plans/{plan_id}`
- `PATCH /api/v1/training-plans/{plan_id}/workouts/{workout_id}`
- `GET|POST /api/v1/activities`
- `GET|POST /api/v1/health-metrics/daily`
- `GET /api/v1/today`
- `GET|POST /api/v1/recommendations`
- `POST /api/v1/recommendations/{recommendation_id}/accept`
- `POST /api/v1/recommendations/{recommendation_id}/reject`
- `POST /api/v1/recommendations/{recommendation_id}/edit`
- `POST /api/v1/recommendations/{recommendation_id}/discuss`
- `POST /api/v1/conversations/messages`
- `POST /api/v1/agent-runs/daily-recommendation`
- `POST /api/v1/agent-runs/training-plan-generation`
- `GET /api/v1/agent-runs`
- `GET /api/v1/agent-runs/{run_id}`
- `GET /api/v1/agent-runs/{run_id}/steps`
- `POST /api/v1/integrations/connections`
- `DELETE /api/v1/integrations/connections/{connection_id}`
- `POST /api/v1/integrations/connections/{connection_id}/admin-token-import`
- `POST /api/v1/integrations/connections/{connection_id}/sync`
- `POST /api/v1/integrations/webhooks/{provider}/{connection_id}`

## Race Goals

`POST /api/v1/races` creates a race goal for the current user. The create payload accepts `name`, `race_date`, `distance_meters`, optional `target_finish_seconds`, and `priority`. It rejects unexpected fields, including `status`; new race goals always start as `planned` server-side.

`PUT /api/v1/races/{race_id}` uses a separate update payload with the same editable race fields plus `status`, and also rejects unexpected fields.

Race goal priority values are `primary`, `secondary`, and `tune_up`.
