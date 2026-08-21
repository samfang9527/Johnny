# Persistence Schema

## Purpose

Define the MVP PostgreSQL persistence model for Johnny, including schema migration workflow, core entity storage, repository boundaries, audit-oriented records, constraint coverage, JSON payload limits, SSO identity persistence, Garmin integration lifecycle data, integration resource cursors, live payload verification, and persistence test coverage.

## Requirements

### Requirement: Migration Workflow

The system SHALL provide an Alembic migration workflow for creating and evolving the PostgreSQL schema from versioned migration files.

#### Scenario: Migrating an empty database

- **GIVEN** an empty PostgreSQL database is available through the documented database URL
- **WHEN** the migration upgrade command is run
- **THEN** all MVP persistence tables are created successfully
- **AND** the migration version table records the applied revision

### Requirement: Core Entity Persistence

The system SHALL persist MVP entities needed for the training recommendation loop with stable identifiers and audit timestamps.

#### Scenario: Creating core records

- **GIVEN** the database schema has been migrated
- **WHEN** records for a user, athlete profile, race, training plan, workout, activity, health metric, recommendation, and agent run are created
- **THEN** each record is stored with a UUID identifier
- **AND** each record stores created and updated timestamps where the entity is mutable

### Requirement: Table Group Coverage

The system SHALL include tables for identity, external auth identities, athlete context, races, plans, workouts, plan adjustments, activities, health metrics, analytics snapshots, recommendations, agent runs, agent run steps, agent context sources, memory, integrations, integration resource cursors, outbox events, notification intents, notification deliveries, and sync runs.

#### Scenario: Metadata contains MVP tables

- **WHEN** tests inspect the SQLAlchemy metadata
- **THEN** every MVP table group is represented by an explicit table
- **AND** each table has named columns for fields that later services must filter, join, sort, or constrain

### Requirement: Repository Boundary

The system SHALL access persisted MVP entities through repository interfaces and unit-of-work boundaries rather than direct database session access from application services.

#### Scenario: Loading a training plan

- **GIVEN** a training plan exists for a user with associated workouts
- **WHEN** an application service requests the current plan through a repository
- **THEN** the repository returns the plan and its workouts
- **AND** the service does not receive or manage the database session directly

### Requirement: Audit-Oriented Records

The system SHALL preserve status and history fields for recommendations, plan adjustments, outbox events, agent runs, sync runs, and notifications.

#### Scenario: Recommendation decision recorded

- **GIVEN** a recommendation exists
- **WHEN** the user accepts, rejects, or edits it
- **THEN** the decision state is persisted
- **AND** the decision timestamp is persisted

#### Scenario: Agent run is traceable

- **GIVEN** an agent run executes tools or produces a recommendation
- **WHEN** the run record is persisted
- **THEN** its status, timestamps, trigger, workflow, prompt version, model/provider metadata, token usage, latency, summaries, and trace reference are available for later inspection

#### Scenario: Agent execution steps are traceable

- **GIVEN** an agent run builds context, calls tools, and makes model calls
- **WHEN** those steps are persisted
- **THEN** each step stores a sequence number, type, name, status, timing, optional token usage, optional tool name, summaries, errors, and a flexible payload
- **AND** dashboard queries can inspect slow or failed steps without parsing a large run trace blob

#### Scenario: Agent context sources are traceable

- **GIVEN** an agent run uses activity, health, memory, training plan, or race context
- **WHEN** context sources are persisted
- **THEN** each source records its type, identifier, summary, optional relevance score, and metadata
- **AND** later explanations can show what evidence contributed to a recommendation

### Requirement: Constraint Coverage

The system SHALL enforce required relationships, uniqueness rules, and status values needed for MVP data integrity.

#### Scenario: Duplicate provider activity rejected

- **GIVEN** an integration activity already exists for a provider connection and provider activity identifier
- **WHEN** another activity is created with the same provider connection and provider activity identifier
- **THEN** the database rejects the duplicate record

#### Scenario: Orphan workout rejected

- **GIVEN** no training plan exists for a referenced training plan identifier
- **WHEN** a workout is created for that missing training plan
- **THEN** the database rejects the workout record

#### Scenario: Duplicate SSO subject rejected

- **GIVEN** an auth identity already exists for a provider, issuer, and subject
- **WHEN** another auth identity is created with the same provider, issuer, and subject
- **THEN** the database rejects the duplicate auth identity

### Requirement: JSON Payload Boundaries

The system SHALL use JSON fields only for flexible evidence payloads, provider summaries, tool-call traces, outbox payloads, and metadata that are not core query fields.

#### Scenario: Queryable field is modeled as a column

- **WHEN** a field is required for filtering, sorting, joining, or enforcing uniqueness
- **THEN** the field is represented as a typed table column
- **AND** it is not stored only inside a JSON payload

### Requirement: SSO Identity Persistence

The system SHALL persist SSO provider identities separately from Johnny application users without coupling the schema to one auth broker.

#### Scenario: Google identity linked directly

- **GIVEN** a Johnny user exists
- **WHEN** a Google sign-in identity is linked to that user
- **THEN** the provider, issuer, subject, email, and provider claims are persisted
- **AND** the Johnny user identifier remains independent from the Google subject identifier

#### Scenario: Multiple SSO providers supported

- **GIVEN** a Johnny user can sign in through more than one SSO provider
- **WHEN** additional provider identities are linked
- **THEN** each provider identity is persisted as a separate auth identity record for the same user
- **AND** identities can represent direct providers or brokered providers such as Google, GitHub, Firebase Authentication, Auth0, or Clerk

### Requirement: Garmin Connect Credential Lifecycle Persistence

The system SHALL persist Garmin Connect integration credential/session lifecycle metadata without storing raw usernames, passwords, session cookies, token-store JSON, or provider tokens in the database.

#### Scenario: Garmin connection stores credential metadata

- **GIVEN** a Johnny user connects Garmin through the Python `garminconnect` integration boundary
- **WHEN** the Garmin connection is persisted
- **THEN** the provider account identifier, auth scheme, credential format/status, credential secret reference, credential expiry, credential rotation timestamp, and last credential refresh timestamp can be stored
- **AND** the credential secret reference points outside the database to a secret store or uncommitted local token-store file boundary

#### Scenario: Garmin session credential refresh is recorded

- **GIVEN** a Garmin integration connection exists
- **WHEN** the `garminconnect` token-store data is rotated or refreshed
- **THEN** the credential secret reference and credential lifecycle timestamps can be updated without exposing raw credentials or session data in application service records

### Requirement: Integration Resource Cursor Persistence

The system SHALL persist sync progress independently for each data resource under an integration connection.

#### Scenario: Garmin resource cursors tracked independently

- **GIVEN** one Garmin Connect integration connection exposes activities, sleep, steps, heart rate, stress, and SpO2 data
- **WHEN** sync progress is recorded for multiple resource types
- **THEN** each resource stores its own cursor value, sync window, last successful sync timestamp, status, and metadata
- **AND** one resource can fail or lag without marking every other resource as stale or failed
- **AND** the design remains usable by future providers with different resource and cursor shapes

### Requirement: Garmin Payload Schema Verification

The system SHALL provide an opt-in verification step that fetches actual activity and health payloads through `garminconnect==0.3.11` on the Python 3.14 runtime and checks that they can be normalized into the persistence schema.

#### Scenario: Live Garmin payloads fit persistence tables

- **GIVEN** a developer provides Garmin Connect access through environment credentials or a local uncommitted token-store file
- **WHEN** the live Garmin schema probe runs
- **THEN** the probe fetches recent activity and daily health data through the Python `garminconnect` package
- **AND** it emits normalized activity and health metric records with provider identifiers, measured timestamps, metric values, units, and sanitized provider summaries
- **AND** no raw username, password, session cookie, token-store JSON, or token value is written to the database

### Requirement: Persistence Test Coverage

The system SHALL include automated tests for metadata creation, migration execution, repository behavior, relationship loading, and critical constraints.

#### Scenario: Persistence verification runs

- **WHEN** the backend persistence test suite runs with a configured test database
- **THEN** migration tests, repository tests, and constraint tests pass
- **AND** failures identify the affected table group or repository boundary
