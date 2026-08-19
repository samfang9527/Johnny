# Design: Backend API

## Design Status

Discussion required before implementation.

## Approach

Expose product workflows through FastAPI routes after application services exist.

Route groups:

- `/health`
- `/me`
- `/athlete/profile`
- `/races`
- `/training-plans`
- `/workouts`
- `/activities`
- `/health-metrics`
- `/today`
- `/recommendations`
- `/conversations`
- `/integrations/webhooks`

## Design Decisions

- Route handlers call application services, not repositories directly.
- Use typed request and response schemas.
- Return evidence in structured arrays for frontend rendering.
- Use a consistent error response format.
- Keep auth minimal or mocked only if explicitly approved; otherwise add real auth as a separate change.

## Testing Strategy

- Contract tests for each route group.
- Validation tests for invalid payloads.
- Recommendation decision route tests verify domain side effects.
- Webhook route tests use fake provider payloads.
- Today route tests verify full context aggregation.

## Risks

- Building API before domain behavior would force route-driven design. This is why API is late in the order.
- Auth scope can grow quickly and should be controlled.

