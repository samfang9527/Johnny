## Why

Johnny has persistence primitives for users, profiles, races, activities, and training data, but it still lacks product-level domain behavior for modeling who the runner is and what race they are training toward. Implementing the athlete and race domain now gives future training-plan generation, Garmin-informed recommendations, and onboarding flows a validated source of truth.

## What Changes

- Add domain models and value objects for athlete profile, training preferences, and race goals.
- Add validation for MVP training context, including experience level, weekly mileage, preferred training days, maximum runs per week, race date, race distance, and target finish time.
- Add target average pace derivation from race distance and target finish time.
- Add repository/application behavior that maps the domain model to the existing persistence schema from the persistence work.
- Add tests for domain validation, preference updates, target pace derivation, and persistence round trips.
- Keep training plan generation, race strategy, recommendations, and frontend onboarding out of scope for this change.

## Capabilities

### New Capabilities

- `athlete-race-domain`: Represents a runner's baseline training context, preferences, and target race goal with validation and target pace derivation.

### Modified Capabilities

None.

## Impact

- Adds backend domain/application code for athlete profile and race goal behavior.
- Extends persistence repository coverage around `athlete_profiles`, `races`, and related user ownership checks.
- Uses the existing SQLAlchemy models and migrations from the persistence schema work without adding new database tables unless implementation exposes a gap.
- Adds unit and integration tests under backend tests.
