# Design: Implement Persistence Schema

## Context

`02-persistence-schema` follows the project foundation and creates the durable database backbone for Johnny's MVP recommendation loop. The current backend has a PostgreSQL-oriented `DATABASE_URL`, SQLAlchemy in base requirements, a minimal database session helper, and dataclass placeholders for scheduled jobs, job runs, and outbox events. It does not yet have Alembic migrations, SQLAlchemy ORM metadata, PostgreSQL driver dependencies, or database-backed repositories.

This change implements schema infrastructure only. Later changes own business logic for athletes, races, plans, training analytics, recommendations, agent tools, notifications, APIs, and frontend workflows.

## Goals / Non-Goals

**Goals:**

- Add Alembic configuration under `backend` with migrations that target the backend SQLAlchemy metadata.
- Add PostgreSQL driver support for runtime and test database URLs.
- Define SQLAlchemy ORM models for the MVP persistence groups named by `02-persistence-schema`, including provider-neutral SSO identities and Garmin Connect integration credential/session metadata.
- Use UUID primary keys, UTC timestamp fields, explicit status fields, and JSON columns only for flexible evidence, metadata, traces, and provider summaries.
- Add repository interfaces and minimal database-backed implementations for core create/get/list/update workflows needed by later application services.
- Add tests that verify metadata creation, migration execution, core persistence, repository behavior, relationship loading, uniqueness constraints, foreign keys, and important status transitions.
- Document local migration commands in the foundation setup docs.

**Non-Goals:**

- Do not add domain calculations, recommendation generation, agent execution, notification delivery, API endpoints, frontend UI, or Terraform database resources.
- Do not build full repository coverage for every future query shape; implement only the minimal persistence boundaries later changes need.
- Do not store large raw provider payload blobs directly if a reference field is enough for MVP debugging.

## Decisions

### Use SQLAlchemy Declarative Models as the Schema Source

Define the MVP tables as SQLAlchemy declarative ORM models and point Alembic autogeneration at the same metadata. This keeps migrations, metadata tests, and repository implementations aligned.

Alternative considered: hand-write SQL migrations without ORM metadata. That would make repository code and migration drift more likely this early in the project.

### Keep Migrations Under `backend`

Place `alembic.ini`, migration environment code, and revisions inside `backend` so migration commands can run with the same Python path and requirements as the API and tests.

Alternative considered: root-level migration files. That is workable, but the rest of the database code already lives under `backend/src/infrastructure/database`, so backend-owned migration files keep ownership clearer.

### Use UUIDs and UTC Timestamps Everywhere

All primary keys should be UUID values. Shared timestamp columns should store created/updated times in UTC, and domain event timestamps should be timezone-aware at the Python boundary.

Alternative considered: integer primary keys with implicit database timestamps. UUIDs make external references and async workflows easier, while explicit timestamps make audit records easier to reason about in tests.

### Normalize Core Query Fields, Use JSON for Evidence

Use columns for fields the app will filter, join, sort, or constrain. Use JSON for flexible payloads such as recommendation evidence, provider summary data, tool-call traces, integration metadata, and outbox payloads.

Alternative considered: JSON-first tables for faster iteration. That would make constraints and later analytics queries weaker, which conflicts with the trust and audit goal.

### Model SSO Identities Separately From Users

Keep `users` as Johnny's application account record and store external sign-in identities in `auth_identities`. Each identity records provider, issuer, subject, email, and provider claims. This supports direct or brokered SSO providers such as Google, GitHub, Firebase Authentication, Auth0, or Clerk without making any provider subject the primary user key.

Alternative considered: store a single provider UID on `users`. That is simpler, but it blocks multiple sign-in providers per user and mixes application identity with authentication provider identifiers.

### Store Garmin Connect Session Credential Metadata as Secret References

Represent Garmin as an `integration_connections` provider with `auth_scheme`, `credential_secret_ref`, credential format/status, credential expiry, rotation timestamp, and last credential refresh timestamp. The MVP uses the latest `garminconnect` package on the Python 3.14 runtime, which authenticates against Garmin Connect and can save/reuse local token-store data. The database stores only secret references and lifecycle metadata; raw Garmin credentials, local token-store files, cookies, and provider tokens belong in a secret store or uncommitted local file boundary.

Alternative considered: store Garmin credentials or token-store JSON directly in a JSON metadata blob. That would make rotation hard to audit and would put sensitive credentials in a flexible payload that is easy to overexpose.

### Track Provider Resource Sync Progress Separately

Add `integration_resource_cursors` for per-resource sync progress under each provider connection. A Garmin connection can expose activities, steps, sleep, heart rate, stress, SpO2, and future resources, and each stream can have a different cursor, date window, failure state, and freshness. Keeping those cursors outside `integration_connections` prevents the connection row from becoming Garmin-specific while still supporting providers with simpler or richer sync models.

Alternative considered: keep one `last_sync_completed_at` field on `integration_connections`. That is useful for account-level health, but it cannot express "activities are current, sleep failed yesterday, and heart rate needs backfill from last week."

### Verify Schema Shape Against Live Garmin Connect Data

Add an opt-in live probe for `garminconnect` that fetches actual activity and health payloads, normalizes them to the persistence shape, and redacts secret-shaped fields from provider summaries. This probe is not a production sync adapter; it is a schema verification step that can be run with a local token-store file or environment credentials when Garmin access is available.

### Build Repositories Around Application Interfaces

Application services should depend on repository protocols and a unit-of-work boundary. Database-backed implementations should hide SQLAlchemy sessions and return simple records or ORM-backed entities through stable interfaces.

Alternative considered: let services import sessions directly until the domain exists. That creates coupling before the domain changes begin and makes later tests harder.

### Add Agent Observability Tables Before Agent Runtime

Keep `agent_runs` as the top-level execution record with queryable fields for trigger, workflow, prompt version, correlation ID, model/provider, token usage, latency, summaries, error state, and trace references. Add append-only `agent_run_steps` for model calls, tool calls, context-building, and safety checks, plus `agent_context_sources` for the evidence used during a run. This keeps dashboards and debugging queries out of large JSON trace parsing while still allowing flexible payloads for provider-specific details.

Alternative considered: store the entire agent trace in one JSON column until the runtime exists. That is faster initially, but it makes later observability dashboards, latency investigations, cost reporting, and recommendation explanations depend on brittle JSON parsing and backfills.

### Test Both Metadata and Migrations

Use metadata creation tests for fast feedback and migration tests for the actual Alembic workflow. Repository tests should use an isolated test database URL and verify behavior through repository APIs.

Alternative considered: only run Alembic tests. Migration tests are important, but metadata tests catch model-level breakage faster and make failures easier to localize.

## Risks / Trade-offs

- The table set is broad for an early MVP -> keep columns focused on fields required by the listed MVP changes and defer specialized indexes/query fields until consumers exist.
- PostgreSQL-specific tests require local database availability -> use a documented test database URL and keep metadata/unit tests isolated where PostgreSQL is not required.
- Alembic autogeneration can miss semantic intent -> review generated revisions and add explicit constraints, indexes, and defaults where tests require them.
- Repository abstractions can become too generic -> create interfaces around concrete use cases from the MVP sequence, not a universal CRUD layer.
- JSON payloads can hide important data -> only use JSON for evidence, metadata, traces, provider claims, and provider summaries; promote queryable fields to columns.
- Authentication and integration credentials are sensitive -> store credential references and provider claims deliberately, avoid raw Garmin credentials/session data in the database, and keep application user IDs separate from provider subject IDs.

## Migration Plan

1. Add database dependencies and Alembic configuration.
2. Introduce SQLAlchemy base metadata, session factory, common UUID/timestamp/status conventions, and initial ORM models, including auth identities and integration credential lifecycle fields.
3. Generate the initial Alembic revision for the MVP schema and review it into source.
4. Add repository interfaces and minimal SQLAlchemy implementations for core user, athlete, race, plan, activity, recommendation, agent, integration, outbox, and notification records.
5. Add metadata, migration, repository, constraint, SSO, Garmin credential metadata, and Garmin payload normalization tests.
6. Document local migration commands, test database setup, and opt-in live Garmin schema probe commands.
7. Roll back by downgrading the initial Alembic revision or dropping the local development database; no production data migration is in scope.

## Open Questions

- Should raw provider payloads be stored inline as compact JSON summaries or as external object references from the first implementation? This design prefers summary JSON plus optional external reference fields.
- Which repository interfaces should be exposed first if implementation time needs to be reduced? This design prioritizes repositories required for creating and loading the core recommendation loop records.
