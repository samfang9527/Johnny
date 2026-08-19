# Design: Persistence Schema

## Design Status

Discussion required before implementation.

## Approach

Use PostgreSQL as the durable source of truth. Add a migration workflow and model the MVP around explicit tables rather than a generic JSON-first schema.

Core table groups:

- Identity: `users`
- Athlete context: `athlete_profiles`, `memory_items`
- Race and plan: `races`, `training_plans`, `workouts`, `plan_adjustments`
- Data: `activities`, `health_metrics`, `training_metric_snapshots`
- Agent and recommendations: `recommendations`, `agent_runs`
- Async and notifications: `outbox_events`, `notification_intents`, `notification_deliveries`
- Integrations: `integration_connections`, `sync_runs`

## Design Decisions

- Prefer UUID primary keys.
- Store all timestamps in UTC.
- Use normalized columns for core query fields.
- Use JSON fields only for evidence payloads, provider raw summaries, tool-call traces, and flexible metadata.
- Keep raw provider payload references separate if payload size becomes large.

## Testing Strategy

- Migration test creates all tables from an empty database.
- Repository tests cover create, get, list, update status, and relationship loading.
- Constraint tests cover required fields, foreign keys, duplicate provider activity IDs, and status transitions.

## Risks

- Over-modeling too early can slow iteration. This schema should cover MVP behavior only.
- Under-modeling recommendations and agent runs would make trust and debugging harder later.

