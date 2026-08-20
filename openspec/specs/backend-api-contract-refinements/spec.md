# backend-api-contract-refinements Specification

## Purpose
TBD - created by archiving change refine-backend-api-contracts. Update Purpose after archive.
## Requirements
### Requirement: Product APIs use a versioned route prefix
The system SHALL expose product API routes under `/api/v1` and SHALL keep operational health endpoints outside the versioned product API namespace.

#### Scenario: Versioned product route is available
- **WHEN** a caller requests a product route such as `/api/v1/me`
- **THEN** the system routes the request through the product API contract for version 1

#### Scenario: Operational health routes remain unversioned
- **WHEN** a caller requests `/health` or `/ready`
- **THEN** the system responds through the operational health endpoints without requiring `/api/v1`

### Requirement: List APIs return shared paging metadata
The system SHALL return list endpoint responses using a shared envelope with `data` and `paging`, where `paging` contains `limit`, `offset`, and `has_next`.

#### Scenario: List response contains paging metadata
- **WHEN** a caller requests a list endpoint
- **THEN** the response body contains `data` with the returned items and `paging` with the effective `limit`, `offset`, and `has_next` values

#### Scenario: List response omits total-count pagination
- **WHEN** a caller requests a list endpoint
- **THEN** the response body does not include `page_number`, `total_pages`, or `total_count` paging fields

### Requirement: List APIs compute has-next without total counts
The system SHALL compute `has_next` by requesting one more record than the effective `limit` and SHALL return no more than the effective `limit` records to the caller.

#### Scenario: More records exist
- **WHEN** a list endpoint fetches more than the effective `limit` records
- **THEN** the response returns only `limit` items and sets `paging.has_next` to `true`

#### Scenario: No more records exist
- **WHEN** a list endpoint fetches no more than the effective `limit` records
- **THEN** the response returns all fetched items and sets `paging.has_next` to `false`

### Requirement: List APIs use normalized paging parameters
The system SHALL validate list endpoint `limit` and `offset` parameters consistently across product API route groups.

#### Scenario: Caller omits paging parameters
- **WHEN** a caller requests a list endpoint without `limit` or `offset`
- **THEN** the system uses the configured default limit and offset `0`

#### Scenario: Caller requests an invalid page
- **WHEN** a caller provides invalid `limit` or `offset` values
- **THEN** the system returns the standard API validation error envelope

