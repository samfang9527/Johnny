## Context

Feature 05 follows the athlete/race and training-plan domain work. The backend already has persistence tables for `activities`, `health_metrics`, `integration_connections`, and `workouts`, but only limited repository behavior for integration connections and raw activity listing. There is no domain layer that validates completed activity data, derives pace, normalizes daily recovery metrics, or matches activities to planned workouts.

This change should support manual MVP entry first. Provider ingestion from Garmin, Strava, or other integrations remains separate, but the domain and persistence mapping should already carry source/provider identifiers and summary payloads so future ingestion can reuse the same normalized shape.

## Goals / Non-Goals

**Goals:**

- Represent completed running activities with normalized distance, duration, derived pace, heart rate, elevation, source, and optional matched workout id.
- Represent daily health/recovery metrics for sleep, HRV, HRV baseline, resting heart rate, stress score, and source.
- Support source `manual` for user-entered data.
- Preserve provider/source identifiers for future integrations and reject duplicate provider activities.
- Match running activities to planned workouts using a simple user-scoped date-based rule.
- Persist and reload activity and health domain objects through focused repository methods.
- Keep source-specific provider payloads in persistence summary fields rather than leaking them into domain model requirements.

**Non-Goals:**

- No external integration OAuth or provider login flows.
- No Garmin/Strava ingestion jobs.
- No analytics calculations beyond normalization and pace derivation.
- No AI recommendations.
- No frontend forms.
- No advanced workout matching using distance, duration, tolerance windows, or ML.

## Decisions

### Keep Activity And Health Behavior In Domain Objects

Add a domain module for completed activities, daily health metrics, pace derivation, validation, and matching inputs. SQLAlchemy models remain storage adapters.

Rationale: normalization rules should be testable without database sessions and should be reusable by future manual entry, provider ingestion, analytics, and recommendation flows.

Alternative considered: add behavior directly to `ActivityModel` and `HealthMetricModel`. That would be fast initially but would couple provider-independent normalization to persistence.

### Use Manual Source As First-Class MVP Source

Manual entries use source `manual` and do not require provider connection or source activity id. Provider entries require a source identifier that can be mapped to `(provider_connection_id, provider_activity_id)` when persisted.

Rationale: manual entry keeps development and product validation unblocked by Garmin or Strava access, while provider identifiers remain available for future ingestion.

Alternative considered: require provider connections for every activity. That would block MVP testing and user-entered data.

### Derive Pace From Distance And Duration

If average pace is not supplied, derive seconds per kilometer from distance meters and duration seconds. Store derived pace in the domain object and persistence summary payload.

Rationale: the current activity table has distance and duration columns but no pace column. Summary JSON can carry derived values while the domain API exposes normalized pace.

Alternative considered: add a dedicated `average_pace_seconds_per_km` column immediately. That may be useful later for query-heavy analytics, but MVP behavior can start with stable summary keys.

### Store Health Signals As Metric Rows With Stable Types

Represent daily recovery as a domain aggregate, then persist each available signal as a `health_metrics` row with stable metric types such as `sleep_duration_minutes`, `sleep_quality`, `hrv_ms`, `hrv_baseline_ms`, `resting_heart_rate`, and `stress_score`.

Rationale: the existing table is metric-oriented and can support sparse daily data. A domain aggregate gives callers a convenient daily shape without requiring a new database table.

Alternative considered: create a dedicated daily recovery table. That improves daily querying but duplicates the existing metric storage model before analytics requirements are proven.

### Match Activities To Workouts By User And Calendar Date

Add a small matching service that links a running activity to a planned workout for the same user and calendar date when exactly one candidate exists.

Rationale: date-based matching is deterministic and matches the source feature. It avoids guessing when multiple workouts exist on a date.

Alternative considered: match by distance/duration tolerance. That is likely needed later but adds policy questions before real usage data exists.

### Use Existing Flexible Payload Fields

Use `activities.provider_summary` for derived pace, source, elevation, average heart rate, matched workout id, and future provider summaries. Use `health_metrics.provider_summary` for date/source context and future provider summaries.

Rationale: the persistence schema already has flexible JSON payload fields. This avoids migration churn while still enforcing stable domain-level keys and tests.

Alternative considered: add dedicated columns for all normalized fields now. That may become necessary for analytics, but query needs should drive that migration.

## Risks / Trade-offs

- JSON summary fields can drift -> Mitigate with domain serializers/deserializers and tests for stable keys.
- Date-only matching can be ambiguous -> Mitigate by matching only when exactly one planned workout exists for the activity date.
- Manual recovery data can be incomplete -> Mitigate by allowing sparse health metrics and validating only supplied values.
- Provider uniqueness can differ by source -> Mitigate by enforcing source activity ids only for non-manual entries and preserving provider summary payloads for debugging.
- Analytics may later need queryable pace/recovery columns -> Mitigate by using stable metric types and summary keys that can be backfilled into columns later.

## Migration Plan

No migration is expected for the first implementation because `activities.provider_summary` and `health_metrics.provider_summary` can hold normalized extension fields, and `provider_activity_id` already supports duplicate provider protection. If workout matching requires a dedicated foreign key, add the smallest migration and update metadata/parity tests.

Rollback is code-only unless a migration is introduced. Stored activity and health rows remain compatible with the current persistence schema.

## Open Questions

- Should manual activities allow duplicate same-day entries without any deduplication, or should a future UI ask users to confirm possible duplicates?
- Should health metric dates be stored at local noon/UTC midnight or use the user's timezone when converting daily values into `measured_at`?
- Should date-based workout matching skip workouts that are already completed or only consider planned/adjusted workouts?
