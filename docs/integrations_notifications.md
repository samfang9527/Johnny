# Integrations and Notifications

This document describes how provider ingestion and notification delivery use the current persistence schema.

## Provider Sync Flow

```mermaid
sequenceDiagram
    participant Job as Sync Job
    participant Integration as IntegrationStore
    participant Provider as ProviderAdapter
    participant Normalizer as Garmin Normalizer
    participant Activity as ActivityStore
    participant Outbox as OutboxStore

    Job->>Integration: get connection and sync cursor
    Job->>Integration: start sync run
    Job->>Provider: fetch payloads with cursor
    Provider-->>Job: activities, health, next cursor
    loop activity payloads
        Job->>Normalizer: normalize activity
        Job->>Activity: lookup provider_connection_id + source_activity_id
        alt new activity
            Job->>Activity: save activity
            Job->>Outbox: create ActivityIngested
        else duplicate
            Job->>Job: increment duplicate count
        end
    end
    loop health payloads
        Job->>Normalizer: normalize daily health
        Job->>Activity: replace daily metric rows for supported metric types
    end
    Job->>Integration: advance cursor and complete sync run
```

## Garmin Connect Experimental Login

`POST /api/v1/integrations/garmin/connect` is the Garmin-specific connection endpoint. It accepts Garmin email, password, and an explicit `global` or `china` region, then delegates credential validation and account discovery to a Garmin login adapter. The endpoint never accepts a user-entered Garmin provider account ID; it persists the provider account identity returned by Garmin and stores only the Garmin profile display name for account recognition.

The production adapter uses the pinned `garminconnect==0.3.11` dependency. The password is used only during the in-memory exchange. Session/token material is serialized from the `garminconnect` client, encrypted through the integration credential cipher, and stored in `integration_credentials`; `integration_connections` remains metadata and keeps `credential_secret_ref` empty for this mode.

Local/private Garmin login requires `GARMIN_CREDENTIAL_MASTER_KEY` to be set to a valid Fernet key. Generate one with `./.venv/bin/python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode("ascii"))'` and store it in `backend/.env`; never commit the real key. `GARMIN_CREDENTIAL_KEY_ID` defaults to `local-fernet` and can be changed when rotating keys.

Garmin sync decrypts the stored session payload only inside the handler call, passes that JSON string directly to `Garmin.login(tokenstore=...)`, and never writes decrypted token JSON to disk. After each successful resource fetch, the adapter serializes the refreshed `garminconnect` session and saves it back through the encrypted credential store. Normal tests override the Garmin adapters and credential cipher so they remain network-free; live Garmin validation remains opt-in through the schema probe.

Garmin sync treats expired, revoked, MFA-blocked, or otherwise credential-blocked sessions as a reauth state: the connection remains connected for historical provenance, but `credential_status` becomes `requires_reauth` and future sync work must wait for a user/admin reconnect action. Garmin rate limits and temporary blocking errors are recorded as failed sync summaries with redacted error text and provider backoff metadata when available; they do not mark credentials as invalid unless the adapter raises a credential-blocked error.

`POST /api/v1/integrations/connections/{connection_id}/sync` triggers a synchronous manual Garmin sync for the active connection. It returns the same connection response shape as Garmin connect, including resource counts, redacted errors, timestamps, partial-failure warnings, and reauth state. If the connection already has a running sync and a started sync run exists, the endpoint returns that running status instead of starting another sync; if the connection is marked running without a matching started run, it returns a conflict.

### Sync windows and review corrections

Scheduled and manual Garmin syncs use the same athlete-local date policy:

- A resource without a usable checkpoint fetches the last 30 dates, including today.
- Subsequent syncs fetch the previous three dates through today. For example, an October 20 sync normally requests October 17–20.
- Each resource advances independently after a successful import. Failed imports and incomplete activity pagination keep their previous checkpoint.
- After an outage, the window also includes the last successfully fetched date and its two preceding dates. This rechecks the last partial day and catches up without truncating a gap to 30 days.
- Checkpoints retain the timezone used for the date range. A changed timezone, malformed checkpoint, or future checkpoint restarts the initial window. Existing date cursors without a timezone remain compatible.

Use `POST /api/v1/integrations/connections/{connection_id}/sync?full_history=true` to explicitly re-fetch the last 30 dates for older missing data. It preserves a longer catch-up window when necessary. The next ordinary sync resumes incremental fetching. It does not delete stored history or change the seven completed dates used by Daily Review; activity coverage is accumulated from successful sync runs.

The scheduled Daily Review still syncs before generating. Evidence changes enqueue corrections against the committed data directly, without another provider sync per historical review. Sync-triggered correction tasks retain `source_sync_run_id` for traceability. Only reviews whose evidence periods intersect the changed dates are corrected.

Restart long-running worker and scheduler processes after deploying backend changes; the development API's automatic reload does not reload those processes. Retire stale processes before starting replacements so all consumers use the same code revision.

`DELETE /api/v1/integrations/connections/{connection_id}` disconnects a Garmin connection by deleting its encrypted credential row and marking the connection `disconnected`. Imported Garmin activities and daily health metrics keep their `provider_connection_id` so historical provenance remains available.

`POST /api/v1/integrations/connections/{connection_id}/admin-token-import` is the backend-only MFA escape hatch for the MVP. It requires `X-Johnny-Admin-Token` to match `JOHNNY_ADMIN_TOKEN`, encrypts the supplied Garmin session payload, stores only non-sensitive lifecycle metadata, and returns the normal redacted connection response.

## Notification Flow

```mermaid
sequenceDiagram
    participant Recommendation as Recommendation Workflow
    participant Notification as NotificationStore
    participant Delivery as Delivery Handler
    participant LINE as LINE Gateway

    Recommendation->>Notification: create notification intent
    Note over Recommendation,Notification: No channel delivery happens during intent creation.
    Delivery->>Notification: load pending or retryable intent
    Delivery->>LINE: deliver formatted payload
    LINE-->>Delivery: provider message id or retryable failure
    Delivery->>Notification: record delivery attempt
    alt success
        Delivery->>Notification: mark intent delivered
    else retryable and attempts remain
        Delivery->>Notification: mark intent retryable
    else terminal
        Delivery->>Notification: mark intent failed
    end
```

## Schema Notes

- `integration_connections.credential_secret_ref` stores only a reference to a token store or secret manager entry. It must not contain Garmin email/password, access tokens, refresh tokens, cookies, or session payloads. Private/self-hosted `garminconnect` mode may store encrypted session/token payloads in a dedicated credential store; Garmin passwords are used only once in memory for session exchange and then discarded. Raw passwords, cookies, unencrypted token-store JSON, and unencrypted provider tokens must not appear in connection metadata, logs, sync summaries, provider summaries, or API responses.
- Disconnect deletes the encrypted credential record, not imported data. Admin token import writes a fresh encrypted credential and marks credentials active without adding a public token-import UI.
- Garmin ingestion is compatible with `garminconnect` payload shapes, but the database schema remains provider-neutral through `provider`, `provider_connection_id`, provider IDs, JSON summaries, and resource cursors.
- `activities` deduplicates imported activities by `provider_connection_id` and `provider_activity_id`.
- Daily health payloads are mapped into the supported `DailyHealthMetrics` fields and persisted as one row per metric type for each day, matching the existing `health_metrics` table design.
- `outbox_events` records `ActivityIngested` only for newly saved provider activities.
- `notification_intents` records what should be sent; `notification_deliveries` records each delivery attempt and provider response.
