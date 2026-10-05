## Purpose
Define backend API behavior for Johnny's async agent workflow trigger and polling routes while preserving the synchronous conversation experience.

## Requirements

### Requirement: Async Agent Trigger Routes
The system SHALL expose dedicated async product workflow trigger routes for daily recommendations and training-plan generation.

#### Scenario: Queue daily recommendation
- **WHEN** the current user posts to `/api/v1/agent-runs/daily-recommendation`
- **THEN** the API creates a queued agent run and queued task atomically
- **AND** returns `run_id`, status `queued`, workflow name `daily_recommendation`, and relative polling URL

#### Scenario: Queue forced daily recommendation rerun
- **WHEN** the current user posts a daily recommendation request with `force=true`
- **THEN** the API enqueues a distinct run with a unique idempotency key
- **AND** does not delete or mutate prior run history

#### Scenario: Queue training plan generation
- **WHEN** the current user posts to `/api/v1/agent-runs/training-plan-generation`
- **THEN** the API validates optional race, date, horizon, plan type, and notes inputs
- **AND** creates a queued run and queued task atomically
- **AND** returns a compact queued response

### Requirement: Agent Run Polling Routes
The system SHALL expose user-scoped agent run polling and step inspection routes.

#### Scenario: Poll queued or completed run
- **WHEN** the current user requests `/api/v1/agent-runs/{run_id}`
- **THEN** the API returns that user's run status, workflow, timestamps, model metadata, summaries, token usage, error summary when present, and recommendation id when present

#### Scenario: Poll run steps
- **WHEN** the current user requests `/api/v1/agent-runs/{run_id}/steps`
- **THEN** the API returns ordered steps for that run
- **AND** does not expose another user's run steps

#### Scenario: List runs for debugging
- **WHEN** the current user requests `/api/v1/agent-runs` with optional workflow name or status filters
- **THEN** the API returns only that user's matching runs

### Requirement: Conversation Remains Synchronous
The system SHALL keep the existing conversation message route synchronous for current MVP conversation UX.

#### Scenario: Submit conversation message
- **WHEN** the current user posts to `/api/v1/conversations/messages`
- **THEN** the route runs the conversation workflow synchronously
- **AND** returns the conversation-visible response or run reference without requiring queue polling

### Requirement: Training Plan API
The API SHALL expose training plans and workouts with structured details while preserving compatibility with existing simple workout fields.

#### Scenario: Creating a manual plan with structured workout steps
- **WHEN** a client posts a training plan whose workouts include structured steps, phase, and coach note
- **THEN** the API validates the payload through the same workout-detail contract used by generated plans
- **AND** stores the plan when the payload is valid

#### Scenario: Returning detailed workout responses
- **WHEN** a client lists or fetches training plans
- **THEN** each workout response includes existing simple fields
- **AND** includes structured steps, phase, coach note, and deterministic compact summary when available

#### Scenario: Returning plan metadata
- **WHEN** a client lists or fetches training plans
- **THEN** each training plan response includes plan version metadata when available
- **AND** generated plans expose their public preparation assessment without private internal evidence
- **AND** legacy or manual plans without an assessment remain readable

#### Scenario: Backward-compatible simple workouts
- **WHEN** a stored workout has no structured steps
- **THEN** the API still returns the existing purpose, distance, duration, pace range, heart-rate zone, and status fields
