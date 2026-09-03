# Database Schema

This document describes the current MVP persistence schema. SQLAlchemy models live in `backend/src/infrastructure/database/models.py`; Alembic uses that metadata as the schema source.

## Design Principles

- UUID string primary keys keep records stable across async jobs, external references, and future services.
- Mutable entities include `created_at` and `updated_at` timestamps through the shared timestamp mixin.
- Queryable, sortable, joinable, and constrained fields are explicit columns.
- JSON columns are reserved for flexible provider payloads, evidence, metadata, traces, and compact summaries.
- Raw secrets are never stored directly. Integration connection metadata stores references to a secret store or uncommitted local token-store boundary. Private/self-hosted Garmin sync may store encrypted session/token payloads in dedicated credential records when that mode is configured; Garmin passwords are used only once in memory for session exchange and then discarded. Raw passwords, cookies, unencrypted token-store JSON, and unencrypted provider tokens must not be stored.

## Entity Relationship Overview

```mermaid
erDiagram
    USERS ||--o| ATHLETE_PROFILES : has
    USERS ||--o{ AUTH_IDENTITIES : signs_in_with
    USERS ||--o{ MEMORY_ITEMS : remembers
    USERS ||--o{ RACES : targets
    USERS ||--o{ TRAINING_PLANS : owns
    RACES ||--o{ TRAINING_PLANS : shapes
    TRAINING_PLANS ||--o{ WORKOUTS : schedules
    TRAINING_PLANS ||--o{ PLAN_ADJUSTMENTS : changes
    TRAINING_PLANS ||--o{ RECOMMENDATIONS : informs
    RECOMMENDATIONS ||--o{ PLAN_ADJUSTMENTS : proposes
    USERS ||--o{ INTEGRATION_CONNECTIONS : connects
    INTEGRATION_CONNECTIONS ||--o| INTEGRATION_CREDENTIALS : secures
    INTEGRATION_CONNECTIONS ||--o{ INTEGRATION_RESOURCE_CURSORS : tracks
    INTEGRATION_CONNECTIONS ||--o{ ACTIVITIES : imports
    USERS ||--o{ ACTIVITIES : owns
    ACTIVITIES ||--o{ HEALTH_METRICS : explains
    INTEGRATION_CONNECTIONS ||--o{ HEALTH_METRICS : imports
    USERS ||--o{ HEALTH_METRICS : owns
    USERS ||--o{ TRAINING_METRIC_SNAPSHOTS : summarizes
    USERS ||--o{ RECOMMENDATIONS : receives
    RECOMMENDATIONS ||--o{ AGENT_RUNS : produced_by
    USERS ||--o{ AGENT_RUNS : runs_for
    AGENT_RUNS ||--o{ AGENT_RUN_STEPS : contains
    AGENT_RUNS ||--o{ AGENT_CONTEXT_SOURCES : uses
    INTEGRATION_CONNECTIONS ||--o{ SYNC_RUNS : executes
    RECOMMENDATIONS ||--o{ NOTIFICATION_INTENTS : notifies
    USERS ||--o{ NOTIFICATION_INTENTS : receives
    NOTIFICATION_INTENTS ||--o{ NOTIFICATION_DELIVERIES : attempts

    USERS {
        string id PK
        string email UK
        string display_name
        string status
        datetime created_at
        datetime updated_at
    }

    AUTH_IDENTITIES {
        string id PK
        string user_id FK
        string provider
        string issuer
        string subject
        string email
        json provider_claims
    }

    ATHLETE_PROFILES {
        string id PK
        string user_id FK,UK
        string timezone
        string experience_level "nullable beginner/intermediate/advanced"
        json metadata_json
    }

    MEMORY_ITEMS {
        string id PK
        string user_id FK
        string memory_type
        string content
        string source
    }

    RACES {
        string id PK
        string user_id FK
        string name
        date race_date
        int distance_meters
        string status
    }

    TRAINING_PLANS {
        string id PK
        string user_id FK
        string race_id FK
        string name
        string status
        date starts_on
        date ends_on
    }

    WORKOUTS {
        string id PK
        string training_plan_id FK
        date scheduled_for
        string workout_type
        int planned_duration_minutes
        string status
        json details
    }

    PLAN_ADJUSTMENTS {
        string id PK
        string training_plan_id FK
        string recommendation_id FK
        string status
        json adjustment_payload
    }

    INTEGRATION_CONNECTIONS {
        string id PK
        string user_id FK
        string provider
        string provider_account_id UK
        string provider_display_name
        string auth_scheme
        string credential_secret_ref
        string credential_format
        string credential_status
        datetime credential_expires_at
        datetime credential_rotated_at
        datetime last_credential_refresh_at
        string sync_status
        json capabilities
        json provider_metadata
    }

    INTEGRATION_CREDENTIALS {
        string id PK
        string integration_connection_id FK,UK
        string credential_format
        string encrypted_payload
        string key_id
        json lifecycle_metadata
        datetime created_at
        datetime updated_at
    }

    INTEGRATION_RESOURCE_CURSORS {
        string id PK
        string integration_connection_id FK
        string resource_type
        json cursor_value
        datetime sync_from
        datetime sync_until
        datetime last_successful_sync_at
        string status
        json metadata_json
    }

    ACTIVITIES {
        string id PK
        string user_id FK
        string provider_connection_id FK
        string provider_activity_id
        datetime started_at
        string activity_type
        float distance_meters
        int duration_seconds
        json provider_summary
    }

    HEALTH_METRICS {
        string id PK
        string user_id FK
        string activity_id FK
        string provider_connection_id FK
        string provider_metric_id
        datetime measured_at
        string metric_type
        float value
        string unit
        json provider_summary
    }

    TRAINING_METRIC_SNAPSHOTS {
        string id PK
        string user_id FK
        datetime captured_at
        string snapshot_type
        json metrics
    }

    RECOMMENDATIONS {
        string id PK
        string user_id FK
        string training_plan_id FK
        string title
        string rationale
        string status
        string decision
        datetime decision_at
        json evidence
    }

    AGENT_RUNS {
        string id PK
        string user_id FK
        string recommendation_id FK
        string status
        string provider
        string model
        string trigger_type
        string workflow_name
        string prompt_version
        string correlation_id
        int latency_ms
        int total_tokens
        int estimated_cost_cents
        string trace_ref
        json trace
        json metadata_json
    }

    AGENT_RUN_STEPS {
        string id PK
        string agent_run_id FK
        int sequence_number
        string step_type
        string name
        string status
        int latency_ms
        int input_tokens
        int output_tokens
        string tool_name
        json payload
    }

    AGENT_CONTEXT_SOURCES {
        string id PK
        string agent_run_id FK
        string source_type
        string source_id
        string source_summary
        float relevance_score
        json metadata_json
    }

    SYNC_RUNS {
        string id PK
        string integration_connection_id FK
        string status
        datetime started_at
        datetime finished_at
        json summary
    }

    NOTIFICATION_INTENTS {
        string id PK
        string user_id FK
        string recommendation_id FK
        string channel
        string status
        datetime scheduled_for
        json payload
    }

    NOTIFICATION_DELIVERIES {
        string id PK
        string notification_intent_id FK
        string status
        string provider
        string provider_message_id
        datetime attempted_at
        json response
    }
```

## Domain Areas

### Identity and Athlete Context

`users` is the stable Johnny account record. External sign-in providers are modeled through `auth_identities`, keyed by provider, issuer, and subject. This keeps Google, GitHub, Firebase-brokered auth, Auth0, Clerk, or future SSO providers separate from Johnny's application user ID.

`athlete_profiles` stores user-level running context. `memory_items` stores durable personalization facts that future agent flows can read through application tools.

### Training Plan and Recommendation Loop

`races`, `training_plans`, `workouts`, and `plan_adjustments` model the plan side of the MVP loop. `recommendations` records the user-facing AI recommendation and the user's decision. `plan_adjustments` can link back to the recommendation that proposed the change.

### Integration and Garmin Data

`integration_connections` represents access to a provider account, not a specific data stream. For Garmin Connect, use:

- `provider`: `garmin_connect`
- `auth_scheme`: `garminconnect_tokenstore`
- `credential_format`: `garminconnect-session-json`
- `credential_secret_ref`: empty for private encrypted-session mode, or a non-sensitive external credential reference for future modes

Private/self-hosted `garminconnect` mode stores encrypted Garmin session/token payloads in `integration_credentials`. Each record belongs to one `integration_connections` row and stores `credential_format`, `encrypted_payload`, `key_id`, timestamps, and only non-sensitive lifecycle metadata such as Garmin region or display name. The local/private MVP Fernet key comes from `GARMIN_CREDENTIAL_MASTER_KEY`; `GARMIN_CREDENTIAL_KEY_ID` identifies the active key for rotation/audit. Garmin credential operations fail with a configuration error if this key is absent or invalid, while unrelated app behavior remains available.

The connection row remains metadata: it must not contain Garmin passwords, cookies, unencrypted token-store JSON, or unencrypted provider tokens. Garmin passwords are used only once in memory for session exchange and then discarded.

`integration_resource_cursors` tracks independent sync progress for each provider resource, such as `activities`, `sleep`, `hrv`, `resting_heart_rate`, `stress`, and `body_battery`. This lets one resource fail or lag without making the whole connection stale.

`activities` and `health_metrics` store normalized imported data. Provider-specific fields that are useful for debugging but not central to querying stay in `provider_summary`.

### AI Observability

`agent_runs` is the top-level execution record. It keeps queryable dashboard fields such as trigger, workflow, prompt version, provider, model, token usage, latency, cost, summaries, errors, and trace references.

`agent_run_steps` records ordered context-building, model-call, tool-call, formatting, and safety-check steps. This avoids parsing one large trace blob for latency and failure analysis.

`agent_context_sources` records the evidence used by an agent run, such as activity, health metric, plan, memory, race, or workout context. This supports future "why did the AI recommend this?" explanations.

### Sync, Outbox, and Notifications

`sync_runs` records provider sync job attempts. `outbox_events` supports reliable asynchronous side effects. `notification_intents` records planned notifications and `notification_deliveries` records provider delivery attempts.

## Constraint Highlights

- `auth_identities` enforces uniqueness by provider, issuer, and subject.
- `integration_connections` enforces one provider account per provider/provider account identifier.
- `integration_credentials` enforces one encrypted credential payload per integration connection.
- `integration_resource_cursors` enforces one cursor per integration connection and resource type.
- `activities` deduplicates by provider connection and provider activity identifier.
- `health_metrics` deduplicates provider metrics by provider connection and provider metric identifier.
- `agent_run_steps` enforces one step per agent run and sequence number.
- `recommendations` constrains status and decision values.
