## Context

Feature 04 follows project foundation, persistence schema, and athlete/race domain work. The backend already has persistence tables and a basic `SqlAlchemyTrainingPlanRepository` for `training_plans` and `workouts`, plus `plan_adjustments` storage. It does not yet have domain objects that validate training calendars, workout details, status transitions, or adjustment proposal behavior.

This change should establish manual/imported training plan behavior first. AI-generated plans, automatic recommendations, activity matching, and frontend calendar rendering depend on this foundation but remain outside this implementation.

## Goals / Non-Goals

**Goals:**

- Represent training plans owned by a user and optionally linked to a race goal.
- Represent dated planned workouts in calendar order.
- Validate plan date ranges and workout dates against plan boundaries.
- Validate supported MVP workout types and planned workout details.
- Enforce controlled workout status transitions.
- Represent adjustment proposals with before/after payloads that do not mutate workouts until explicitly applied.
- Persist and reload plans, workouts, and adjustment proposals through focused repository methods.
- Preserve tenant safety by requiring user-scoped repository access for plan reads and writes.

**Non-Goals:**

- No AI-generated plan construction.
- No automatic recommendation or plan adjustment application.
- No frontend calendar UI.
- No Garmin or other activity matching.
- No training load analytics or fitness scoring.
- No medical interpretation of workout or injury context.

## Decisions

### Keep Training Plan Behavior In Domain Objects

Add a domain module for training plans, workouts, status transitions, and adjustment proposals. SQLAlchemy models remain storage adapters.

Rationale: plan validation and transition rules need deterministic unit tests and should not require database sessions. This follows the athlete/race domain pattern already introduced.

Alternative considered: keep behavior directly on `TrainingPlanModel` and `WorkoutModel`. That would be faster for the first repository test but would couple product behavior to SQLAlchemy and make worker/API usage harder to test.

### Start With Manual Or Imported Plans

The first implementation creates and stores explicit plan/workout data supplied by a caller. It does not generate plans from race distance, athlete profile, or AI output.

Rationale: Johnny needs a trustworthy schedule object before it can evaluate or adjust plans intelligently. Generation can be layered later on top of the same domain contract.

Alternative considered: generate a starter plan in this feature. That adds premature training methodology decisions and makes correctness harder to evaluate.

### Use Controlled Status Transitions

Represent workout statuses as a lifecycle with allowed transitions:

- `planned` -> `completed`
- `planned` -> `skipped`
- `planned` -> `adjusted`
- `adjusted` -> `completed`
- `adjusted` -> `skipped`

Rationale: these transitions cover MVP behavior while preventing ambiguous transitions such as reverting completed workouts without an explicit future correction/audit feature.

Alternative considered: allow any status change. That is simpler but weakens auditability and future recommendation confidence.

### Preserve Original Planned Details During Adjustments

Adjustment proposals store before/after payloads and status. A proposal does not mutate the workout until it is applied by an explicit command.

Rationale: users should be able to review proposed changes, and future AI observability/recommendation flows need clear evidence of what changed and why.

Alternative considered: directly mutate workouts when proposing. That is operationally simpler but loses trust and makes declined recommendations impossible to audit.

### Use Existing Flexible Workout Details

Use `workouts.details` for workout purpose, distance, pace range, heart-rate zone, original planned values, and future extension fields. Use `plan_adjustments.adjustment_payload` for before/after proposal snapshots.

Rationale: the persistence schema already includes JSON payloads for MVP flexibility. This avoids migration churn while workout structure is still evolving.

Alternative considered: add dedicated columns for distance, pace, and heart-rate zone now. Those may become worthwhile later for query-heavy analytics, but MVP domain behavior can proceed with stable payload keys.

### Expand TrainingPlanRepository As The Focused Storage Boundary

Extend the split `training_plan_repository` module with domain-oriented methods for saving/loading plans with workouts and creating/listing adjustment proposals. Reads and writes should be scoped by user id.

Rationale: the codebase now uses focused repository modules. Keeping plan behavior in the training plan repository avoids growing a new monolith and gives future services one clear persistence boundary.

Alternative considered: create separate workout and adjustment repositories immediately. That may be useful later, but MVP workflows operate on a plan aggregate.

## Risks / Trade-offs

- JSON workout details can drift -> Mitigate with domain serializers/deserializers and tests for stable keys.
- Status lifecycle may need correction flows later -> Mitigate by making the transition table explicit and adding future correction behavior as a separate change.
- Plan date validation can reject useful edge cases -> Mitigate by allowing workouts on both start and end dates and keeping imported/generated distinction out of scope.
- Adjustment proposals can become too generic -> Mitigate by requiring before/after payloads and validating proposal status.
- Repository methods can leak cross-user data -> Mitigate by requiring user id on plan aggregate reads/writes and testing ownership filtering.

## Migration Plan

No migration is expected for the first implementation because `training_plans`, `workouts.details`, and `plan_adjustments.adjustment_payload` already exist. If implementation reveals a required persistence gap, add the smallest Alembic migration and update metadata/parity tests.

Rollback is code-only unless a migration is introduced. Stored training plan and workout rows remain compatible with the existing schema.

## Open Questions

- Should imported plans and manually created plans be represented by a `source` field now or deferred until integration import work?
- Should completed workout actuals be stored in `workouts.details` for MVP, or wait for activity matching?
- Should plan adjustment application be included in this change or limited to proposal creation and status transitions?
