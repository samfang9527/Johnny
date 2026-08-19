## Why

Johnny now has athlete, race, and training plan domains, but it still needs normalized completed activity and daily recovery data before analytics and recommendations can reason about training execution. Implementing the activity and health domain now gives the product a manual data path and a stable normalization boundary while Garmin and other provider ingestion remain separate work.

## What Changes

- Add domain models for completed activities and daily health/recovery metrics.
- Add manual activity entry behavior using source `manual`, with normalized distance, duration, pace, heart rate, elevation, and optional matched workout fields.
- Add pace derivation from distance and duration when average pace is not supplied.
- Add daily health metric behavior for sleep, HRV, HRV baseline, resting heart rate, stress score, and source.
- Add duplicate provider activity protection using provider/source identifiers while allowing manual entries.
- Add date-based activity-to-workout matching against existing planned workouts.
- Connect domain behavior to existing `activities`, `health_metrics`, and training plan/workout persistence.
- Keep external integration OAuth, provider-specific ingestion, analytics scoring, AI recommendations, and frontend forms out of scope.

## Capabilities

### New Capabilities

- `activity-health-domain`: Represents normalized completed activities, daily recovery metrics, duplicate provider activity protection, and basic activity-to-workout matching.

### Modified Capabilities

None.

## Impact

- Adds backend domain/application code for activity, health metric, and matching behavior.
- Extends the focused activity repository with domain-oriented methods for activities and health metrics.
- Uses existing persistence tables where possible; implementation may add the smallest metadata or linking field only if required for workout matching.
- Adds backend unit and repository/service integration tests.
