## Context

Feature 03 depends on the project foundation and the persistence schema. The backend currently has SQLAlchemy storage models for `users`, `athlete_profiles`, `races`, and related training data, but there is no domain layer that validates runner context, normalizes race goals, or derives values such as target pace.

The implementation should add product-level behavior without coupling it to API routes, frontend onboarding, training-plan generation, or Garmin ingestion. Persistence models remain infrastructure concerns; domain objects should be usable in unit tests without a database.

## Goals / Non-Goals

**Goals:**

- Represent athlete profile data needed by future training decisions.
- Represent athlete preferences such as preferred training days, long-run day, and maximum runs per week.
- Represent race goals with distance, race date, target finish time, priority, status, and derived target pace.
- Persist and reload athlete profile and race goal records through repository methods using the existing database schema.
- Validate domain values before they are stored.
- Keep metric values as the internal calculation format while allowing unit preference to be recorded.

**Non-Goals:**

- No generated training plan.
- No race strategy engine.
- No AI recommendation behavior.
- No Garmin activity ingestion or schema changes.
- No frontend onboarding UI or public API endpoints unless implementation needs a small internal contract for tests.
- No medical interpretation of injury notes.

## Decisions

### Keep Domain Objects Separate From SQLAlchemy Models

Create domain dataclasses or similarly lightweight Python objects under a backend domain package, with persistence mapping handled by repository methods.

Rationale: validation and target pace calculations should be testable without database sessions. SQLAlchemy models already represent storage structure, and adding domain rules directly to them would couple product behavior to persistence.

Alternative considered: add methods directly to `AthleteProfileModel` and `RaceModel`. This is simpler initially but makes future API, worker, and AI workflows harder to test independently.

### Store Flexible Preferences In Profile Metadata

Use the existing `athlete_profiles.metadata_json` column for preference details that are not first-class columns yet: current weekly mileage, preferred training days, preferred long-run day, maximum runs per week, unit preference, training preferences, and injury notes.

Rationale: the persistence schema intentionally includes JSON extension fields for MVP flexibility. This avoids a migration before onboarding fields settle while still validating the shape at the domain boundary.

Alternative considered: add dedicated columns now. That improves queryability but risks churn while the product is still discovering which profile fields are stable.

### Keep Metric Units Internal

Normalize mileage and race distance to metric units internally. Store the user's unit preference as metadata for later presentation.

Rationale: calculations such as target pace and future training load should use one canonical unit system. UI/API layers can convert later.

Alternative considered: store mixed units exactly as entered. That preserves input fidelity but pushes conversion complexity into every downstream training calculation.

### Model Race Goal Behavior Around Existing Race Records

Use `races.distance_meters`, `races.race_date`, `races.status`, and metadata-backed fields for target finish time, priority, and derived target pace when existing columns are insufficient.

Rationale: the current schema already supports the stable identifiers and core race fields. Metadata-backed target details keep this change compatible with the current database while still enforcing domain validation.

Alternative considered: migrate the races table now for target finish time and priority. That may be useful later if these fields become heavily queried, but the current change can proceed without introducing migration risk.

### Repository Methods Enforce User Ownership

Add repository behavior for creating/updating/loading athlete profiles and race goals by user id. Race lookup and update paths must include user ownership checks.

Rationale: future API and worker flows will rely on these methods to avoid leaking or mutating another user's race/profile data.

Alternative considered: expose generic model access and let callers filter. That spreads authorization-sensitive filtering across call sites.

## Risks / Trade-offs

- Flexible metadata can hide schema drift -> Mitigate with domain serializers/deserializers and tests that assert the expected metadata keys.
- Future reporting may need queryable target fields -> Mitigate by keeping metadata key names stable so a later migration can backfill columns.
- Race date validation depends on "today" -> Mitigate by injecting today's date into validators in tests rather than reading wall-clock time directly.
- Onboarding could request too much data -> Mitigate by separating required MVP fields from optional notes/preferences.
- Injury notes could be misread as medical data -> Mitigate by storing them only as user-provided cautionary context and not adding diagnostic behavior.

## Migration Plan

No database migration is expected for the first implementation because `athlete_profiles`, `races`, and `metadata_json` already exist. If implementation reveals a required column gap, add the smallest Alembic migration and update schema parity tests.

Implementation can be rolled back by removing the new domain/repository code and tests. Any profile or race rows created through the new behavior remain compatible with the existing persistence schema.

## Open Questions

- Should MVP allow only standard race distances, or any positive custom distance in meters?
- Which experience levels should be accepted for the first onboarding flow?
- Should one race per user be marked as the active goal, or should active selection wait for training-plan generation?
