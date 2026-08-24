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
- Garmin ingestion is compatible with `garminconnect` payload shapes, but the database schema remains provider-neutral through `provider`, `provider_connection_id`, provider IDs, JSON summaries, and resource cursors.
- `activities` deduplicates imported activities by `provider_connection_id` and `provider_activity_id`.
- Daily health payloads are mapped into the supported `DailyHealthMetrics` fields and persisted as one row per metric type for each day, matching the existing `health_metrics` table design.
- `outbox_events` records `ActivityIngested` only for newly saved provider activities.
- `notification_intents` records what should be sent; `notification_deliveries` records each delivery attempt and provider response.
