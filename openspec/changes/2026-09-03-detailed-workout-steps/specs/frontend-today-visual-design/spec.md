## MODIFIED Requirements

### Requirement: Today Workout Card
The Today workout card SHALL remain workout-first and scannable while showing executable detail when structured workout steps are available.

#### Scenario: Showing a compact structured summary
- **GIVEN** today's workout includes structured steps
- **WHEN** the Today screen renders
- **THEN** the workout card shows a compact deterministic summary such as `15 min warmup + 4 x (800m interval / 400m easy) + 10 min cooldown`
- **AND** the summary does not replace the workout purpose or status

#### Scenario: Opening workout detail
- **GIVEN** today's workout includes structured steps
- **WHEN** the user opens workout details
- **THEN** a view-only modal shows the ordered steps, nested repeat blocks, target zones, computed target snapshots, and optional coach note

### Requirement: Calendar Workout List
The calendar workout list SHALL support structured workout previews without becoming dense or unreadable.

#### Scenario: Showing detailed schedule rows
- **GIVEN** a scheduled workout includes a compact structured summary
- **WHEN** the schedule list renders
- **THEN** the row may show the compact summary along with existing date, workout type, purpose, distance or duration, pace, and status information

#### Scenario: Rendering legacy workouts
- **GIVEN** a workout has no structured steps
- **WHEN** Today or schedule UI renders it
- **THEN** the UI preserves the current simple workout display
