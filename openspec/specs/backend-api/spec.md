## Purpose
Define backend API behavior for Johnny's async review, requested workout advice, training-plan generation, and owner-scoped polling routes.

## Requirements

### Requirement: Async Agent Trigger Routes
The system SHALL expose independent retrospective review and requested workout-advice workflows plus training-plan generation.

#### Scenario: Legacy manual route adapts to Workout Advice
- **WHEN** the current user posts to `/api/v1/agent-runs/daily-recommendation`
- **THEN** the API accepts only the current athlete-local date and queues the same `workout_advice` workflow as `/api/v1/johnny/workout-advice`
- **AND** it returns a run id and relative polling URL without scheduling a legacy combined Daily Advice result

#### Scenario: Queue requested advice
- **WHEN** the athlete posts `/api/v1/johnny/workout-advice` with a request UUID, target workout, and structured constraints
- **THEN** the API reserves the date/workout slot and queues sync before generation
- **AND** a transport retry with the same request UUID/body returns the same run; conflicting body or concurrent request receives 409

#### Scenario: Read independent Johnny outputs
- **WHEN** the athlete reads `/api/v1/johnny/overview`
- **THEN** `daily_review` and `workout_advices` are separate fields with separate revisions and attempt states, alongside current actionable proposals
- **AND** the GET does not enqueue work

#### Scenario: Queue training plan generation
- **WHEN** the current user posts to `/api/v1/agent-runs/training-plan-generation`
- **THEN** the API validates optional race, date, horizon, plan type, and notes inputs
- **AND** creates a queued run and queued task atomically
- **AND** returns a compact queued response

### Requirement: Agent Run Polling Routes
The system SHALL expose user-scoped agent run polling and step inspection routes.

#### Scenario: Poll queued or completed run
- **WHEN** the current user requests `/api/v1/agent-runs/{run_id}`
- **THEN** the API returns that user's run status, workflow, timestamps, model metadata, summaries, token usage, error summary when present, and nullable review/advice/recommendation ids

### Requirement: Date-scoped coaching read
The system SHALL expose a concise current Workout Advice slot through Today while retaining the old Daily Advice field as a nullable transition read.

#### Scenario: Read current advice
- **WHEN** the athlete requests `/api/v1/today?anchor_date=YYYY-MM-DD`
- **THEN** `workout_advice` is that athlete's latest requested advice slot for the requested date, or null
- **AND** `daily_advice` remains nullable for transition clients but is not used by the new Johnny UI

#### Scenario: Refresh fails
- **WHEN** activity sync or advice generation fails after a prior successful version
- **THEN** the previous advice revision remains stored with a stale freshness or failure state
- **AND** no new advice revision is published

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
