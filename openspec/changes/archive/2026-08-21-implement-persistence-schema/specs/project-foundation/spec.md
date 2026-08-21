# Delta for Project Foundation

## ADDED Requirements

### Requirement: Database Migration Commands

The system SHALL document local commands for applying database migrations and verifying the current migration state.

#### Scenario: Developer applies local migrations

- **GIVEN** a developer has configured the documented local PostgreSQL database URL
- **WHEN** they run the documented migration upgrade command
- **THEN** the local database schema is upgraded to the latest migration revision

#### Scenario: Developer checks migration state

- **GIVEN** a developer has configured the documented local PostgreSQL database URL
- **WHEN** they run the documented migration status command
- **THEN** the current database revision is reported without starting the API server
