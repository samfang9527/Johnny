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
- `POST /api/v1/integrations/connections/{connection_id}/sync` uses independent resource checkpoints: 30 dates initially, then the previous three dates through today, with catch-up after missed syncs. Optional query parameter `full_history=true` requests a 30-date backfill (or the longer outstanding catch-up window). Dates use the athlete's timezone.

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
- `GET /api/v1/activities/detail-coverage`
- `GET /api/v1/activities/{activity_id}/execution?analysis_id=...`
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

## Coaching analysis and activity evidence

Johnny overview, review, advice, and history responses retain their existing envelopes and `current.guidance` / `current.narrative` strings. New revisions add `current.analysis`; their slots also expose `analysis_mode` (`llm` or `rules`). Legacy revisions have no `analysis` or `analysis_mode` field. Slot `freshness` (`current` or `stale`) describes the published coaching result, independently of its analysis mode. `/api/v1/today?anchor_date=YYYY-MM-DD` still includes `workout_advice` and now includes a short `workout_advice_summary` with `advice_id`, `advice_date`, `freshness`, and `guidance`; structured revisions add `headline`, `summary`, and `analysis_mode` to that summary.

Examples of the additive fields (each is the `data` inside its usual envelope):

```json
{"freshness":"current","analysis_mode":"llm","current":{"guidance":"今天先保守執行。","analysis":{"schema_version":"coaching-analysis-v2","headline":"留意今天的恢復","summary":"先依體感保守執行。","analysis_mode":"llm","fallback_reason":null}}}
```

```json
{"freshness":"current","analysis_mode":"rules","current":{"narrative":"先確認活動與課表配對。","analysis":{"schema_version":"coaching-analysis-v2","headline":"先確認執行情況","summary":"資料不足以解讀各段差異。","analysis_mode":"rules","fallback_reason":"disabled"}}}
```

```json
{"freshness":"stale","analysis_mode":"llm","current":{"narrative":"先依當時證據檢視這堂課。","analysis":{"analysis_mode":"llm"}}}
```

```json
{"freshness":"current","current":{"narrative":"舊版回顧文字。","score":{"value":null}}}
```

These examples are field excerpts; real coaching slots and analyses include their other existing fields. `analysis_mode=rules` identifies the generation fallback, not poor activity coverage. A stale result may still have been generated successfully by an LLM. The seven-day execution score remains a separate deterministic field.

`POST /api/v1/johnny/reviews/{review_id}/retry` accepts an optional body `{"source":"stored_evidence"}` or `{"source":"sync"}`. `stored_evidence` queues generation directly from committed evidence and does not call Garmin. An omitted body defaults to `sync` only when the prior attempt was `sync_failed`; otherwise it defaults to `stored_evidence`. The original review publication date and timezone are reused, including for historical stale reviews. Requesting a different source while a retry is already queued or running returns 409.

`GET /api/v1/activities/{activity_id}/execution` returns the latest immutable execution analysis for an owned activity, or `analysis: null`, `analysis_id: null`, and `freshness: "unavailable"` when none exists. `analysis_id` selects that exact historical analysis for the same owned activity. Its `used_details` are loaded by the analysis's stored snapshot IDs; `current_details` reports today's fetch pointers separately. `freshness` is `current` only when the selected analysis is latest and all its snapshot IDs still match the current pointers. A changed pointer or an older selected analysis yields `stale`. Missing or unowned activities and analyses return 404. The response contains segment summaries, facts, findings, mapping and coverage, but no FIT payload, GPS or raw samples.

For example, a partial chart source remains explicitly sampled even if all available chart points were covered:

```json
{"activity_id":"run-1","analysis_id":"analysis-1","freshness":"stale","analysis":{"activity_id":"run-1","activity_ids":["run-1"],"fingerprint":"example","prescription_revision_id":null,"snapshot_ids":["snapshot-1"],"mapping":"estimated","facts":[],"findings":[],"limitations":["sampled_chart"],"algorithm_version":"execution-analysis-v1"},"used_details":[{"snapshot_id":"snapshot-1","activity_id":"run-1","resource":"fit","coverage":{"state":"partial","sampling":"chart","covered_seconds":900,"missing_channels":["heart_rate"],"limitations":[]},"precision":"sampled","segments":[]}],"current_details":[]}
```

`GET /api/v1/activities/detail-coverage` returns owner-only `total_activities`, `with_details`, `without_details`, and separate `fetch_status_counts`, `coverage_state_counts`, and `sampling_counts`. Counts for coverage and sampling use current snapshots; they do not imply that an activity has a precise, complete recording.

## Race Goals

`POST /api/v1/races` creates a race goal for the current user. The create payload accepts `name`, `race_date`, `distance_meters`, optional `target_finish_seconds`, and `priority`. It rejects unexpected fields, including `status`; new race goals always start as `planned` server-side.

`PUT /api/v1/races/{race_id}` uses a separate update payload with the same editable race fields plus `status`, and also rejects unexpected fields.

Race goal priority values are `primary`, `secondary`, and `tune_up`.
