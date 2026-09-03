## Why

Generated training plans currently persist workouts as simple calendar rows with type, purpose, duration, distance, optional pace range, and optional heart-rate zone. That is not enough for athletes to execute key workouts. For example, an interval workout should specify warmup, repeat distances, recoveries, target efforts, and cooldown.

The system also needs plan continuity across race preparation. Rolling regeneration should feel like the same coach continuing a race plan, not a new isolated plan each week.

## What Changes

- Add structured workout steps as the canonical workout-detail representation for generated key workouts.
- Support step types `warmup`, `work`, `recovery`, `cooldown`, `repeat`, `drill`, `stride`, `hill`, and `free_run`.
- Represent repeat blocks with `repeat_count` and nested steps.
- Support target kinds `pace`, `heart_rate`, and `rpe`, with pace zones limited to `easy`, `steady`, `marathon`, `threshold`, `interval`, `repetition`, and `rpe_only`.
- Compute target snapshots inside trusted application/write-tool boundaries rather than letting the LLM own exact pace math.
- Build a pace profile from athlete baseline data, using threshold pace when available, race target pace and recent activity pace only as low-confidence fallback, and RPE-only targets when confidence is low.
- Persist optional LLM-authored `coach_note`, limited to non-canonical guidance.
- Add deterministic compact workout summaries derived from structured steps.
- Add training-plan metadata JSON for plan version continuity, including `plan_series_id`, `previous_plan_id`, and continuity summaries.
- Expose structured steps through existing training plan API responses.
- Render detailed steps in the frontend through Today preview and a workout detail modal.

## Capabilities

### Modified Capabilities

- `training-plan-domain`: Structured workout steps, targets, pace profile use, plan phase, weekly rationale, and plan-version metadata semantics.
- `agent-runtime-tools`: Training-plan generation context preload, LLM tool contract, enrichment, validation, repair, and fallback behavior.
- `persistence-schema`: Training plan metadata JSON and workout details JSON usage for structured steps.
- `backend-api`: Request/response schema exposure for workout steps, coach notes, phases, summaries, and plan metadata.
- `frontend-today-visual-design`: Today card workout preview and detail modal rendering.

## Impact

- Affects backend domain models, application services, agent tools, local/OpenAI gateway schemas, persistence mapping, API schemas/routes, frontend data mapping, frontend UI, tests, and docs.
- Does not require a `workout_steps` table in V1.
- Does not add full structured workout editing in V1.
- Does not make LLM text the canonical workout summary.
