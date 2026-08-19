## Context

Johnny already has user-scoped training plans, workouts, completed activities, daily health metrics, and a `training_metric_snapshots` table. The next layer needs deterministic metrics that can feed recommendations and Today UI without relying on LLM arithmetic or provider-specific payload shapes.

The analytics layer must operate on normalized domain objects from the activity/health and training-plan domains. Garmin-specific ingestion remains outside this change; analytics should not know whether data came from Garmin, manual entry, or another future provider.

## Goals / Non-Goals

**Goals:**

- Calculate repeatable training load metrics: weekly distance, previous weekly distance, mileage ramp percentage, acute load, chronic load, and acute-to-chronic ratio.
- Calculate recovery context from available daily health metrics: sleep debt, HRV delta from baseline, resting heart rate delta from baseline, stress, and a conservative readiness label.
- Aggregate Today context from current plan/workout state, recent activities, recovery context, and explicit evidence values.
- Persist and reload training analytics snapshots through the existing `training_metric_snapshots` model.
- Keep all reads and writes tenant-scoped by `user_id`.

**Non-Goals:**

- No LLM-generated recommendations or coaching prose.
- No race prediction model, VO2 max estimation, or advanced physiology model.
- No frontend charts or API endpoints.
- No provider-specific parsing or Garmin sync behavior.
- No new database migration unless implementation discovers a missing column in the current schema.

## Decisions

### Deterministic Application Service Boundary

Create analytics value objects and services under the domain/application boundary, with infrastructure repositories only responsible for fetching normalized inputs and persisting snapshots.

Rationale: formulas are core business logic and need isolated unit tests. Keeping formulas out of SQLAlchemy repositories prevents persistence concerns from deciding training semantics.

Alternative considered: calculate everything directly in repository SQL. That would be efficient for aggregates but harder to unit test, harder to reuse for in-memory fixtures, and more likely to leak database-specific behavior into domain rules.

### MVP Formula Definitions

Use simple documented formulas first:

- Weekly distance: sum of completed running activity distance from `anchor_date - 6 days` through `anchor_date`.
- Previous weekly distance: sum from the immediately preceding 7-day window.
- Mileage ramp percentage: `(weekly_distance - previous_weekly_distance) / previous_weekly_distance * 100`; unavailable when previous distance is zero or missing.
- Acute load: sum of recent load over the last 7 days. MVP load uses duration minutes and can later evolve to HR/RPE-weighted load.
- Chronic load: average weekly load over the last 28 days. MVP reports unavailable when the window has no activity.
- Acute-to-chronic ratio: acute load divided by chronic weekly load, unavailable when chronic load is zero.

Rationale: these formulas are transparent, testable, and sufficient as recommendation evidence. They avoid false precision while the product is still collecting real activity and health data.

Alternative considered: start with TRIMP, power-based load, or advanced strain models. Those require richer inputs and would create misleading gaps for users who only sync basic Garmin activity summaries.

### Conservative Recovery Labels

Represent recovery as evidence plus a coarse readiness label such as `ready`, `caution`, `rest`, or `unknown`. Missing required signals must be marked unavailable and must not be silently scored as zero.

Use these MVP thresholds:

- Sleep target is 480 minutes until user-specific sleep targets exist.
- HRV delta uses `hrv_ms` versus `hrv_baseline_ms` when both are available; a drop of 5% or more is caution evidence and a drop of 10% or more is rest evidence.
- Resting heart rate baseline is derived from prior daily health metrics when available; an increase of 3 bpm or more is caution evidence and 5 bpm or more is rest evidence.
- Stress score of 50 or more is caution evidence and 70 or more is rest evidence.
- Acute-to-chronic ratio above 1.2 is caution evidence and above 1.5 is rest evidence.
- Readiness is `unknown` when fewer than two recovery/load signals are available, `rest` when any rest-level signal exists or at least two caution-level signals exist, `caution` when one caution-level signal exists, and `ready` otherwise.

Rationale: recovery labels can affect training decisions, so the first version should explain exactly which signals contributed. `unknown` is preferable to an invented score when health data is incomplete.

Alternative considered: produce a numeric readiness score for every day. That would look precise but would hide missing inputs and invite unsafe interpretation.

### Today Context Aggregator

Build a `TodayContextService` that composes:

- The current active plan and workouts relevant to the anchor date.
- Recent completed activities and matched workout references.
- Training load metrics.
- Recovery context.
- Explicit missing-data markers and source evidence.

Rationale: future recommendation and UI layers need one structured payload for "what Johnny knows today" while preserving source metrics. This service should return data, not prose.

Alternative considered: make each caller gather its own context. That duplicates date windows and missing-data logic across recommendations, API, and frontend work.

### Snapshot Persistence

Persist calculated analytics as `TrainingMetricSnapshotModel` rows with `snapshot_type`, `captured_at`, `user_id`, and JSON `metrics`. Initial snapshot types should distinguish at least `training_load`, `recovery_context`, and `today_context`.

Rationale: the current persistence schema already includes flexible snapshot storage. JSON keeps early analytics evolvable while tests can still assert required keys.

Alternative considered: add typed columns for every metric now. That would make queries simpler but would force frequent migrations while formula names and evidence payloads are still changing.

## Risks / Trade-offs

- Training load formulas may be too simple for advanced athletes -> document formulas in tests and keep snapshot metric names versionable.
- Missing health data may produce frequent `unknown` readiness -> expose missing signals explicitly so future UI can explain what needs syncing.
- JSON snapshots are less queryable than typed columns -> keep canonical calculations in services and add typed tables later only after metrics stabilize.
- Date-window boundaries can be surprising across time zones -> accept an explicit `anchor_date` and use date-based windows for MVP; defer user-timezone policy to API/user-profile work.
- Analytics could accidentally mix tenant data -> require all repository methods to accept trusted `user_id` and filter by it.

## Migration Plan

No schema migration is expected because `activities`, `health_metrics`, `training_plans`, `workouts`, and `training_metric_snapshots` already exist. Implementation should add repository methods and tests that verify snapshots are written and loaded using the current models. If a missing index or constraint appears during performance work, propose it as a separate persistence change.

## Open Questions

- None for MVP. Future changes can refine formulas, user-specific baselines, and scheduled snapshot generation after real usage data exists.
