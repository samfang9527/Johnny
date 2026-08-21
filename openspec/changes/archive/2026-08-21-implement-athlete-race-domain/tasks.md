## 1. Domain Models

- [x] 1.1 Add backend domain package structure for athlete and race objects.
- [x] 1.2 Add athlete profile and preference value objects with timezone, experience level, weekly mileage, preferred training days, long-run day, maximum runs per week, unit preference, training preferences, and injury notes.
- [x] 1.3 Add race goal value objects with name, race date, distance meters, optional target finish time, priority, status, and optional derived target pace.
- [x] 1.4 Add domain validation errors and deterministic validation helpers that accept the validation date as an input.

## 2. Domain Tests

- [x] 2.1 Add unit tests for valid athlete profile creation and preference updates.
- [x] 2.2 Add unit tests rejecting negative weekly mileage and maximum runs per week lower than preferred training day count.
- [x] 2.3 Add unit tests for valid race goal creation with and without target finish time.
- [x] 2.4 Add unit tests rejecting past race dates and non-positive race distances.
- [x] 2.5 Add unit tests for target average pace derivation from distance and target finish time.

## 3. Persistence Mapping

- [x] 3.1 Add repository protocol methods for saving, loading, and updating athlete profiles by user id.
- [x] 3.2 Add repository protocol methods for creating, listing, loading, and updating race goals by user id.
- [x] 3.3 Implement SQLAlchemy mapping between athlete domain objects and `AthleteProfileModel`, including stable metadata keys for flexible preference fields.
- [x] 3.4 Implement SQLAlchemy mapping between race goal domain objects and `RaceModel`, including stable metadata keys for target finish time, priority, and derived target pace if no dedicated columns exist.
- [x] 3.5 Ensure race goal repository reads and writes are scoped by user id for ownership protection.

## 4. Persistence Tests

- [x] 4.1 Add repository round-trip tests for athlete profile creation, loading, and preference updates.
- [x] 4.2 Add repository round-trip tests for race goal creation, listing, loading, target pace persistence, and user ownership filtering.
- [x] 4.3 Update existing repository or metadata tests only if implementation exposes a required persistence schema gap.

## 5. Verification

- [x] 5.1 Run focused domain and repository tests for the athlete and race implementation.
- [x] 5.2 Run the backend test suite.
- [x] 5.3 Run OpenSpec validation for the change.
