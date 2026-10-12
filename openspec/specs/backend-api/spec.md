## Purpose
Define backend API behavior for Johnny's async agent workflow trigger and polling routes while preserving the synchronous conversation experience.

## Requirements

### Requirement: Async Agent Trigger Routes
The system SHALL expose dedicated async product workflow trigger routes for Daily Advice and training-plan generation.

#### Scenario: Queue Daily Advice
- **WHEN** the current user posts to `/api/v1/agent-runs/daily-recommendation`
- **THEN** the API creates a queued agent run and `daily_advice.sync` task atomically
- **AND** returns `run_id`, status `queued`, workflow name `daily_recommendation`, and relative polling URL
- **AND** successful completion produces Daily Advice without a pending Recommendation

#### Scenario: Queue forced daily recommendation rerun
- **WHEN** the current user posts a daily recommendation request with `force=true`
- **THEN** the API enqueues a distinct run with a unique idempotency key
- **AND** does not delete or mutate prior run history
- **AND** a successful newer run replaces the current advice for that athlete and local date

#### Scenario: Queue training plan generation
- **WHEN** the current user posts to `/api/v1/agent-runs/training-plan-generation`
- **THEN** the API validates optional race, date, horizon, plan type, and notes inputs
- **AND** creates a queued run and queued task atomically
- **AND** returns a compact queued response

### Requirement: Agent Run Polling Routes
The system SHALL expose user-scoped agent run polling and step inspection routes.

#### Scenario: Poll queued or completed run
- **WHEN** the current user requests `/api/v1/agent-runs/{run_id}`
- **THEN** the API returns that user's run status, workflow, timestamps, model metadata, summaries, token usage, error summary when present, recommendation id when present, and Daily Advice id when present

### Requirement: Date-scoped Daily Advice read
The system SHALL expose one current Daily Advice through the authenticated Today context for the requested athlete-local date.

#### Scenario: Read current advice
- **WHEN** the athlete requests `/api/v1/today?anchor_date=YYYY-MM-DD`
- **THEN** `daily_advice` is that athlete's current advice for the requested date, or null
- **AND** a present value includes state, freshness, generation time, source, plan week, structured facts, execution mode, and three content sections when available

#### Scenario: Refresh fails
- **WHEN** activity sync or advice generation fails after a prior successful version
- **THEN** Today retains the prior content and original generation time with a stale freshness and failure state
- **AND** no additional advice revision appears in the response

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
