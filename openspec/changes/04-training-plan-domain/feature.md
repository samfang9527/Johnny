# Feature 04: Training Plan Domain

## Order

4 of 12. This follows athlete/race domain and precedes activity, analytics, and recommendations.

## Layer

Domain model and core business foundation.

## Goal

Represent a training calendar with planned workouts, statuses, and controlled adjustments.

## Depends On

- `01-project-foundation`
- `02-persistence-schema`
- `03-athlete-race-domain`

## Delivers

- Training plan model
- Workout model
- Workout status lifecycle
- Manual plan creation
- Basic plan adjustment proposal structure

## Non-Goals

- No AI-generated plans
- No automatic recommendation logic
- No frontend calendar UI
- No integration-based workout matching

## Design Discussion Required

Before implementation, discuss `design.md` and confirm:

- Whether MVP starts with manual/imported plans instead of generated plans
- Which workout types are supported first
- How strict workout status transitions should be

## Testable Outcome

Domain tests can create a plan, add workouts, update statuses, and propose an adjustment without applying it automatically.

