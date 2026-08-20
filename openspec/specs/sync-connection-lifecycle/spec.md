# sync-connection-lifecycle Specification

## Purpose
TBD - created by archiving change refine-backend-api-contracts. Update Purpose after archive.
## Requirements
### Requirement: User has one active sync provider
The system SHALL allow at most one active sync provider connection per user.

#### Scenario: First sync provider connection
- **WHEN** a user connects a sync provider and has no active sync provider connection
- **THEN** the system stores that connection with status `active`

#### Scenario: Replacing active sync provider
- **WHEN** a user connects a different sync provider account while another sync provider connection is active
- **THEN** the system marks the previous active connection as `replaced` and stores the new connection as `active`

### Requirement: Existing same-user provider account is reactivated
The system SHALL reactivate an existing connection row when the same user reconnects the same `(provider, provider_account_id)`.

#### Scenario: User switches back to original provider account
- **WHEN** a user reconnects a `(provider, provider_account_id)` that already exists for that user
- **THEN** the system updates that existing row to status `active` instead of creating a duplicate connection row

#### Scenario: Reactivation replaces any other active provider
- **WHEN** reactivating an existing provider account and another sync provider connection is active for the same user
- **THEN** the system marks the other active connection as `replaced`

#### Scenario: Reactivation resets sync cursor state
- **WHEN** the system reactivates an existing provider account
- **THEN** the system resets or marks stale that connection's resource cursors so the next sync can perform a safe lookback

### Requirement: Provider accounts are globally unique
The system SHALL enforce one owner for each non-empty `(provider, provider_account_id)` across all users.

#### Scenario: Provider account belongs to another user
- **WHEN** a user attempts to connect a `(provider, provider_account_id)` that already belongs to another user
- **THEN** the system rejects the request with a conflict error

#### Scenario: Provider account id is required for sync connections
- **WHEN** a user attempts to create a sync provider connection without `provider_account_id`
- **THEN** the system rejects the request with the standard API validation error envelope

### Requirement: Historical provider data keeps provenance
The system SHALL preserve replaced sync provider connection rows so historical imported activity and health data can retain source provenance.

#### Scenario: Replaced connection remains available for historical records
- **WHEN** a sync provider connection is replaced
- **THEN** the system does not hard delete that connection row or imported records linked to it

#### Scenario: Historical records remain linked to original connection
- **WHEN** a user views or processes historical activity and health data imported before provider replacement
- **THEN** the records still reference the provider connection that produced them

