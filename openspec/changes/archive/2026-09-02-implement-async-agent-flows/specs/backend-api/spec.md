## ADDED Requirements

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
