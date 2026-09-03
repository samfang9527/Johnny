## MODIFIED Requirements

### Requirement: Agent Runtime Persistence
The system SHALL persist agent runtime queue and observability data with schema constraints compatible with local SQLite tests and future PostgreSQL deployment.

#### Scenario: Agent persistence tables migrate
- **WHEN** migrations are applied to an empty database
- **THEN** the database supports queued agent runs, agent task persistence, active and superseded generated training plans, and recommendation observability
