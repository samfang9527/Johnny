## 1. Approval

- [x] 1.1 Review this change's `design.md` with the product owner.
- [x] 1.2 Confirm approval before implementation starts.

## 2. Domain And Pace Profile

- [x] 2.1 Add typed workout-step, target, repeat-block, coach-note, phase, and summary behavior to the training-plan domain.
- [x] 2.2 Add typed athlete baseline accessors for threshold pace stored in `AthleteProfile.training_preferences`.
- [x] 2.3 Add deterministic pace-profile calculation from threshold pace, race target pace, and recent activity fallback sources.
- [x] 2.4 Add structural and totals validation for workout steps, including nested repeat totals.
- [x] 2.5 Add deterministic compact workout summary formatting from steps.

## 3. Persistence

- [x] 3.1 Add `metadata_json` to `training_plans` through SQLAlchemy model and Alembic migration.
- [x] 3.2 Persist and load workout steps, phase, coach note, target snapshots, and plan metadata through `SqlAlchemyTrainingPlanRepository`.
- [x] 3.3 Preserve legacy workouts without steps and synthesize display-only `free_run` details at read/render boundaries.

## 4. Agent Runtime

- [x] 4.1 Preload athlete profile, baseline, races, recent activity summary, key sessions, last active plan context, and pace profile into training-plan generation requests.
- [x] 4.2 Expand `createTrainingPlan` local/OpenAI tool schemas to accept structured workout steps, targets, coach notes, phase, weekly rationales, and plan metadata.
- [x] 4.3 Enrich raw LLM target zones into computed pace/heart-rate/RPE snapshots inside `createTrainingPlan`.
- [x] 4.4 Keep one model repair attempt, then create an athlete-adjusted deterministic fallback plan on validation failure.
- [x] 4.5 Preserve plan continuity metadata when creating a new race-plan version.

## 5. Backend API

- [x] 5.1 Extend training plan request and response schemas with workout steps, coach note, phase, compact summary, and plan metadata.
- [x] 5.2 Allow manual training plan creation to accept the same structured workout payload contract.
- [x] 5.3 Keep existing simple workout fields backward compatible.

## 6. Frontend

- [x] 6.1 Extend frontend workout types and API mapping for steps, coach notes, phases, compact summaries, and plan metadata.
- [x] 6.2 Render compact summaries in the Today workout card and schedule rows when structured steps are available.
- [x] 6.3 Add a view-only workout detail modal for full step structure and coach note.
- [x] 6.4 Keep legacy/simple workouts readable with current distance, duration, pace, and purpose display.

## 7. Tests And Docs

- [x] 7.1 Add unit tests for workout-step validation, repeat totals, pace-profile confidence behavior, summary formatting, and coach-note length.
- [x] 7.2 Add repository and migration tests for `training_plans.metadata_json` and workout details JSON round trips.
- [x] 7.3 Add agent runtime tests for context preload, tool schema validation, enrichment, one repair attempt, fallback template creation, and plan continuity metadata.
- [x] 7.4 Add API tests for structured workout request/response compatibility.
- [x] 7.5 Add frontend tests for compact summary rendering and workout detail modal behavior.
- [x] 7.6 Update active specs and docs after implementation.
- [x] 7.7 Run focused backend/frontend tests and the relevant full suite before archiving the change.
