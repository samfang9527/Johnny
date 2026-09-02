## MODIFIED Requirements

### Requirement: Table Group Coverage
The system SHALL include tables for identity, external auth identities, athlete context, races, plans, workouts, plan adjustments, activities, health metrics, analytics snapshots, recommendations, agent runs, agent run steps, agent context sources, agent tasks, memory, integrations, integration resource cursors, outbox events, notification intents, notification deliveries, and sync runs.

#### Scenario: Metadata contains MVP tables
- **WHEN** tests inspect the SQLAlchemy metadata
- **THEN** every MVP table group is represented by an explicit table
- **AND** each table has named columns for fields that later services must filter, join, sort, or constrain

### Requirement: Audit-Oriented Records
The system SHALL preserve status and history fields for recommendations, plan adjustments, agent tasks, outbox events, agent runs, sync runs, and notifications.

#### Scenario: Recommendation decision recorded
- **GIVEN** a recommendation exists
- **WHEN** the user accepts, rejects, or edits it
- **THEN** the decision state is persisted
- **AND** the decision timestamp is persisted

#### Scenario: Queued agent task is traceable
- **GIVEN** an async agent workflow is queued
- **WHEN** the task record is persisted
- **THEN** its task type, status, correlation id, idempotency key, payload, availability, claim, completion, failure, retry, and error-summary fields are available for local inspection

#### Scenario: Agent run is traceable
- **GIVEN** an agent run executes tools or produces a recommendation
- **WHEN** the run record is persisted
- **THEN** its status, timestamps, trigger, workflow, prompt version, model/provider metadata, token usage, latency, summaries, and trace reference are available for later inspection

## ADDED Requirements

### Requirement: Local Agent Task Queue Persistence
The system SHALL persist local async agent work in an `agent_tasks` table with AWS-like envelope fields and retry lifecycle state.

#### Scenario: Queued task persists envelope
- **WHEN** an async workflow is triggered
- **THEN** the task row stores task type, payload, correlation id, idempotency key, created timestamp, and status `queued`

#### Scenario: Duplicate scheduled task blocked
- **GIVEN** a queued or completed scheduled daily recommendation task exists for a user and anchor date
- **WHEN** the scheduler attempts to enqueue the same idempotency key again
- **THEN** the database-backed queue prevents a duplicate task

#### Scenario: Force rerun records distinct task
- **WHEN** a forced daily recommendation rerun is requested
- **THEN** the task row uses a distinct idempotency key
- **AND** prior task and run history remains unchanged

#### Scenario: Failed task becomes dead-lettered
- **GIVEN** a retryable task exceeds its maximum attempts
- **WHEN** the queue records the final failure
- **THEN** the task status becomes `dead_lettered`
- **AND** retry count, last error type, last error message, and failed timestamp are persisted

### Requirement: Async Agent Migration Coverage
The system SHALL include one coherent migration for async agent flow schema changes.

#### Scenario: Migrating async agent schema
- **GIVEN** an empty or existing MVP database is available
- **WHEN** the migration upgrade command is run
- **THEN** the database supports queued agent runs, agent task persistence, draft and superseded training plans, and training-plan-creation recommendations
- **AND** SQLite-compatible tests and optional PostgreSQL migration tests verify the schema behavior
