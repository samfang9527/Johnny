# Design: Training Plan Domain

## Design Status

Discussion required before implementation.

## Approach

Start with manual or imported training plans. Do not build AI plan generation in this feature.

Training plan:

- Belongs to a user
- May target a race
- Has start and end dates
- Has one active version
- Contains dated workouts

Workout:

- Has type, purpose, date, distance or duration, pace range, heart-rate zone, and status
- Supports status transitions
- Keeps original planned values when adjusted

Plan adjustment:

- Stores before and after payloads
- Has status `proposed`, `approved`, `rejected`, or `applied`
- Requires explicit approval before mutation

## Testing Strategy

- Unit tests for plan date boundaries.
- Unit tests for supported workout types.
- Unit tests for valid and invalid status transitions.
- Unit tests verifying proposals do not mutate workouts before approval.
- Repository tests for plan with workouts.

## Risks

- Generating plans too early will distract from proving recommendation quality.
- Allowing direct mutation without history would weaken trust and auditability.

