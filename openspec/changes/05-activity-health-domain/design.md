# Design: Activity and Health Domain

## Design Status

Discussion required before implementation.

## Approach

Support manual data first and keep provider fields ready for later integrations.

Activity fields:

- Source and source activity ID
- Start time
- Sport type
- Distance
- Duration
- Average pace
- Average heart rate
- Elevation gain
- Matched workout ID

Health metric fields:

- Date
- Sleep duration
- Sleep quality
- HRV
- HRV baseline
- Resting heart rate
- Stress score
- Source

## Design Decisions

- Manual entries use source `manual`.
- Provider entries require `(source, source_activity_id)` uniqueness.
- Activity-to-workout matching starts date-based and can become smarter later.
- Pace is derived from distance and duration when not supplied.

## Testing Strategy

- Unit tests for pace derivation.
- Unit tests for health metric validation.
- Repository tests for duplicate provider activity rejection.
- Service tests for activity-to-workout matching.

## Risks

- Manual recovery data can be incomplete. Later analytics must handle missing signals conservatively.
- Provider payload differences should not leak into domain models.

