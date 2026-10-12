# frontend-today-visual-design Specification

## Purpose

Define the Chinese-first Johnny visual frontend behavior for the Today cockpit, schedule, recommendation decisions, data source binding entry point, and shared UI primitives.

## Requirements

### Requirement: Race preparation assessment in Plan

The Plan view SHALL show a generated race Plan Version's public preparation assessment beside its selected Race Goal, using Traditional Chinese status and explanation text. An older plan without an assessment SHALL remain readable without an invented status.

#### Scenario: Generated plan has a preparation gap
- **WHEN** the athlete views a race plan with a `gap` assessment
- **THEN** the Plan view names the gap and displays its explanation without promising race completion

### Requirement: Chinese-first Johnny app shell

The system SHALL replace the frontend scaffold with a Chinese-first Johnny product shell that follows `DESIGN.md` visual tokens and navigation language.

#### Scenario: User opens the frontend shell

- **WHEN** the user opens the frontend app
- **THEN** the app shows Johnny product navigation with `今日`, `計畫`, `Johnny`, `運動員`, and `資料`
- **AND** the shell uses the `DESIGN.md` light mint start-line palette, typography roles, and focus-visible states

### Requirement: Today decision cockpit

The system SHALL render Today as a decision cockpit that prioritizes race context, recovery evidence, today's workout, Johnny's recommendation, and decision actions.

#### Scenario: User views Today with full context

- **WHEN** Today context is available from the API
- **THEN** the user sees race countdown, recovery signals, today's unchanged workout, current Daily Advice when present, separate pending proposals, evidence, and unavailable signals in Chinese-first copy

#### Scenario: User views Today with sparse data

- **WHEN** Today context is missing recovery, activity, or health signals
- **THEN** the UI shows a clear sparse-data state that identifies missing signals
- **AND** the UI provides a path to `資料` for binding data providers

#### Scenario: Showing a compact structured workout summary

- **GIVEN** today's workout includes structured steps
- **WHEN** the Today screen renders
- **THEN** the workout card shows a compact deterministic summary such as `15 min warmup + 4 x (800m interval / 400m easy) + 10 min cooldown`
- **AND** the summary does not replace the workout purpose or status

#### Scenario: Opening workout detail

- **GIVEN** today's workout includes structured steps
- **WHEN** the user opens workout details
- **THEN** a view-only modal shows the ordered steps, nested repeat blocks, target zones, computed target snapshots, and optional coach note

### Requirement: Current Daily Advice
The system SHALL show one current Daily Advice for the athlete-local date on Today, with all three Traditional Chinese sections reachable without an approval action.

#### Scenario: Advice is ready
- **WHEN** Today includes a ready Daily Advice
- **THEN** the UI shows its plan-week execution summary, today's workout execution advice, workout guide, generation time, and source freshness
- **AND** the Today Decision follows its validated execution mode without implying that advice changes the planned workout

#### Scenario: Advice is pending or stale
- **WHEN** Daily Advice is pending, failed, or stale after a failed refresh
- **THEN** the UI shows the current state and any earlier successful text with its original generation time and a freshness warning
- **AND** the Today Decision does not contradict the uncertain advice

#### Scenario: Manual sync replaces advice
- **WHEN** a manual Garmin sync returns a Daily Advice run and that run completes
- **THEN** Today refreshes and shows only the new current advice

### Requirement: Recommendation decision strip

The system SHALL display separate approval-backed Recommendation decisions using the `decision strip` pattern from `DESIGN.md`. Daily Advice has no accept or reject controls.

#### Scenario: Pending recommendation is displayed

- **WHEN** a pending recommendation appears on Today
- **THEN** the recommendation visually groups signal, evidence, recommendation, and decision actions
- **AND** the available actions use the labels `接受調整`, `編輯調整`, `保留原課表`, and `討論原因` where applicable

#### Scenario: User accepts a recommendation

- **WHEN** the user chooses `接受調整`
- **THEN** the frontend calls the recommendation accept API
- **AND** the action control enters a stable busy state without changing layout size
- **AND** the displayed status updates after the API returns

### Requirement: Calendar schedule surface

The system SHALL display planned workouts in a calendar-oriented schedule that remains readable on mobile and desktop.

#### Scenario: User opens the schedule view

- **WHEN** planned workouts are available
- **THEN** workouts are grouped by date with type, purpose, distance or duration, pace or heart-rate guidance when available, compact structured summary when available, and status

#### Scenario: User opens the schedule on a narrow viewport

- **WHEN** the viewport is narrow
- **THEN** the schedule uses a list-first layout that preserves workout details and actions without clipping text

#### Scenario: Rendering legacy workouts

- **GIVEN** a workout has no structured steps
- **WHEN** Today or schedule UI renders it
- **THEN** the UI preserves the current simple workout display

### Requirement: Data source binding entry point

The system SHALL provide a first-class `資料` surface for supported provider binding and sync-status guidance.

#### Scenario: User opens data sources

- **WHEN** the user opens `資料`
- **THEN** the UI shows provider cards for Garmin, Apple Health, Strava, and future providers with connection status, signal coverage, and a `連接資料來源` action where supported

#### Scenario: User binds a supported provider

- **WHEN** the user submits provider binding information for a supported MVP provider
- **THEN** the frontend sends the connection request through the integrations connection API
- **AND** the UI communicates that Johnny stores credential references rather than raw provider credentials

### Requirement: Shared visual primitives

The system SHALL implement repeated Today, Calendar, and provider UI through shared visual primitives instead of screen-local duplicates.

#### Scenario: Repeated states are rendered

- **WHEN** buttons, cards, status badges, evidence rows, provider cards, loading states, empty states, or errors appear across the frontend
- **THEN** they use shared components or shared CSS classes mapped to `DESIGN.md` tokens
- **AND** enabled interactive controls expose hover, active, disabled, busy, and keyboard focus-visible states
