# Design: Training Analytics

## Design Status

Discussion required before implementation.

## Approach

Create deterministic services under the application/domain boundary:

- `TrainingLoadService`
- `RecoveryService`
- `TodayContextService`
- `WorkoutCompletionAnalyzer`

Analytics should return structured values and evidence, not prose.

Initial metrics:

- Weekly distance
- Previous weekly distance
- Mileage ramp percentage
- Acute load
- Chronic load
- Acute:chronic ratio
- Sleep debt
- HRV delta from baseline
- Resting HR delta from baseline
- Readiness label

## Design Decisions

- Use fixed fixtures to test formulas.
- Persist daily snapshots after calculation.
- Allow on-demand recalculation for development and backfill.
- Explicitly mark missing inputs.

## Testing Strategy

- Unit tests for every formula.
- Fixture tests for Today context aggregation.
- Snapshot persistence tests.
- Edge case tests for missing data and zero-distance periods.

## Risks

- Training load formulas can become controversial. MVP should use simple documented formulas first.
- Overconfident readiness labels could create safety risk. Labels should be conservative.

