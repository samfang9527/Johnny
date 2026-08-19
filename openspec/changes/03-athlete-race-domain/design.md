# Design: Athlete and Race Domain

## Design Status

Discussion required before implementation.

## Approach

Model athlete and race behavior as domain objects independent of API and persistence details.

Athlete profile should include:

- Experience level
- Current weekly mileage
- Preferred training days
- Preferred long-run day
- Maximum runs per week
- Training preferences
- Injury notes as user-provided context, not medical diagnosis

Race should include:

- Name
- Date
- Distance
- Target finish time
- Priority
- Status
- Derived target average pace

## Design Decisions

- Use metric units internally for MVP.
- Store unit preference but keep calculation logic metric-first.
- Treat injury notes as cautionary context only.
- Keep race strategy out of this feature. This feature only models the goal.

## Testing Strategy

- Unit tests for valid and invalid athlete profile values.
- Unit tests for race distance and date validation.
- Unit tests for target pace derivation from distance and target time.
- Repository round-trip tests use persistence from Feature 02.

## Risks

- Asking for too many onboarding fields can block activation.
- Asking for too few fields can make early recommendations generic.

