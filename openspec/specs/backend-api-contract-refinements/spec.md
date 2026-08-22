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

### Requirement: API Health and User Context
The system SHALL expose backend health and readiness checks and a current-user context endpoint without requiring production SSO for local MVP development.

#### Scenario: Loading current user context
- **WHEN** an authenticated or local test request loads the current user context
- **THEN** the API returns the scoped user id, display name, email when available, and enabled MVP capabilities

#### Scenario: Preserving health checks
- **WHEN** a client requests health or readiness status
- **THEN** the API returns successful status responses compatible with the existing health route behavior

### Requirement: Athlete and Race Routes
The system SHALL expose routes for reading and saving athlete profile data and managing race goals within the current user's tenant scope.

#### Scenario: Saving athlete profile
- **WHEN** the current user submits timezone, experience level, and profile metadata
- **THEN** the API validates the request and returns the saved athlete profile for that user

#### Scenario: Listing race goals
- **WHEN** the current user requests race goals with paging and optional date range filters
- **THEN** the API returns only that user's race goals ordered by race date

#### Scenario: Rejecting invalid race request
- **WHEN** a race creation request omits required date or distance fields
- **THEN** the API rejects it with a structured validation error

### Requirement: Training Plan and Workout Routes
The system SHALL expose routes for creating, reading, listing, and updating training plans and workouts for the current user.

#### Scenario: Loading training plan detail
- **WHEN** the current user requests a training plan detail
- **THEN** the API returns the plan, its workouts, linked race when present, and plan status

#### Scenario: Updating workout status
- **WHEN** the current user updates a workout status
- **THEN** the API applies domain validation and returns the updated workout state

#### Scenario: Hiding another user's training plan
- **WHEN** a user requests a training plan owned by another user
- **THEN** the API returns a not-found error rather than the other user's data

### Requirement: Activity and Health Routes
The system SHALL expose routes for listing, creating, and reading activities and daily health metrics for the current user.

#### Scenario: Listing activities with paging and date range
- **WHEN** the current user requests activities with paging and optional start date filters
- **THEN** the API returns only matching activities for that user with provider source metadata

#### Scenario: Saving manual activity
- **WHEN** the current user submits a manual activity
- **THEN** the API validates activity distance, duration, sport type, and start time before returning the saved activity

#### Scenario: Loading daily health metrics
- **WHEN** the current user requests daily health metrics for a date range
- **THEN** the API returns supported health metric values grouped by metric date

### Requirement: Today Context Route
The system SHALL expose a Today context route that aggregates athlete, race, plan, workout, activity, health, analytics, and recommendation context for the current user.

#### Scenario: Loading Today context
- **WHEN** a user has a profile, race, active training plan, workout, activity data, health data, analytics, and recommendations
- **THEN** the API returns the next race, today's workout, recovery evidence, recent training context, and current recommendation

#### Scenario: Loading Today context with sparse data
- **WHEN** the current user has not yet connected all MVP data sources
- **THEN** the API returns a successful response with missing sections represented as null or empty arrays, not a server error

### Requirement: Recommendation Decision Routes
The system SHALL expose routes for listing recommendations and accepting, rejecting, editing, and discussing pending recommendations.

#### Scenario: Accepting recommendation by API
- **WHEN** the current user accepts a pending recommendation
- **THEN** the API applies the approved action through the application handler and returns the updated recommendation state

#### Scenario: Rejecting recommendation by API
- **WHEN** the current user rejects a pending recommendation with an optional reason
- **THEN** the API records the decision and returns the updated recommendation state

#### Scenario: Editing recommendation by API
- **WHEN** the current user submits edited recommendation action payload
- **THEN** the API validates and saves the edited decision through the application handler

### Requirement: Conversation Routes
The system SHALL expose conversation entry points for submitting user messages and retrieving conversation-visible responses or run references.

#### Scenario: Submitting conversation message
- **WHEN** the current user sends a conversation message
- **THEN** the API records or dispatches the message through the application boundary and returns a message or run reference

#### Scenario: Rejecting empty conversation message
- **WHEN** a conversation request has no meaningful content
- **THEN** the API rejects it with a structured validation error

### Requirement: Integration Webhook Routes
The system SHALL expose provider-neutral integration webhook routes that hand provider payloads to the ingestion boundary without storing raw credentials.

#### Scenario: Receiving provider activity payload
- **WHEN** an integration webhook receives provider activity payloads for a known connection
- **THEN** the API invokes the provider ingestion workflow and returns sync summary counts

#### Scenario: Receiving duplicate provider payload
- **WHEN** a webhook delivers a provider activity already stored for the same connection
- **THEN** the API returns a successful summary with duplicate counts and does not create another activity event

#### Scenario: Rejecting unknown provider connection
- **WHEN** a webhook references a missing or unauthorized integration connection
- **THEN** the API returns a not-found or unauthorized structured error without processing payloads

### Requirement: Structured API Errors
The system SHALL return a consistent structured error format for validation failures, missing resources, conflicts, and domain validation errors.

#### Scenario: Domain validation failure
- **WHEN** a route receives syntactically valid input that violates a domain rule
- **THEN** the API returns an error object with code, message, and details suitable for frontend display

#### Scenario: Request validation failure
- **WHEN** a route receives malformed JSON or missing required fields
- **THEN** the API returns a structured validation error preserving field-level details
