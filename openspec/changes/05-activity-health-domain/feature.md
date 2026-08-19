# Feature 05: Activity and Health Domain

## Order

5 of 12. This follows training plan modeling and precedes analytics.

## Layer

Domain model and data normalization foundation.

## Goal

Represent completed running activities and daily recovery signals in normalized MVP formats.

## Depends On

- `01-project-foundation`
- `02-persistence-schema`
- `03-athlete-race-domain`
- `04-training-plan-domain`

## Delivers

- Activity model
- Health metric model
- Manual activity entry
- Manual health/recovery entry
- Activity-to-workout matching rules
- Duplicate provider activity protection

## Non-Goals

- No external integration OAuth
- No analytics calculations beyond basic normalization
- No AI recommendations
- No frontend forms

## Design Discussion Required

Before implementation, discuss `design.md` and confirm:

- MVP required activity fields
- MVP required recovery fields
- How manual entries should be labeled
- Activity matching tolerance for planned workouts

## Testable Outcome

Domain and repository tests can create manual activities and health metrics, normalize values, prevent duplicates, and match an activity to a planned workout.

