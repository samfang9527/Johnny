# Feature 03: Athlete and Race Domain

## Order

3 of 12. This follows persistence and precedes training-plan behavior.

## Layer

Domain model.

## Goal

Represent the runner and their target race clearly enough to drive a training plan and future recommendations.

## Depends On

- `01-project-foundation`
- `02-persistence-schema`

## Delivers

- Athlete profile domain model
- Athlete preferences model
- Race goal model
- Race target pace derivation
- Validation for race and profile inputs

## Non-Goals

- No generated training plan
- No race strategy engine
- No recommendations
- No frontend onboarding UI

## Design Discussion Required

Before implementation, discuss `design.md` and confirm:

- Target MVP athlete type
- Required onboarding fields
- Race distance formats
- Metric-only MVP or unit conversion support

## Testable Outcome

Domain tests validate athlete profile creation, preference updates, race goal creation, and target pace calculation.

