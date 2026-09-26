# Johnny Training Plan Generation

## Purpose

Johnny should generate complete, safe, race-aware training plan versions that become the user's Active Projection without requiring a full preview step. The product must let the athlete manually regenerate a plan from the frontend, keep plans continuous through background generation, and guarantee that generated workouts contain structured execution details the frontend can render.

## Source Decisions

- Manual regeneration uses a thin frontend sheet to choose the Race Strategy or Aerobic Maintenance Block, then queues generation.
- The generated result directly becomes the new Active Projection when it passes validation.
- The previous Active Projection becomes `superseded` in the same transaction that saves the new valid projection.
- New manual projections start tomorrow; they do not rewrite today's planned workout.
- Each generated Plan Version covers at most 16 weeks.
- Race-based projections end on race day. Post-race rest is represented by a Recovery Window, not by adding recovery weeks to the race projection.
- Johnny deterministic planning owns the Plan Skeleton, workout dates, weekly structure, phase coverage, quota safety, and completeness.
- The LLM may enrich coaching intent, workout purposes, coach notes, and structured key-session workout steps, but it must not change workout dates or weekly structure.
- Incomplete generated output must never be saved as an Active Projection.
- `hill` is a canonical workout type in V1.

## Domain Language

This spec uses the terms in `CONTEXT.md`, especially:

- Race Strategy
- Plan Series
- Plan Version
- Active Projection
- Plan Phase
- Phase Segment
- Plan Skeleton
- Hard Session
- Hard Session Capacity
- Completion Repair
- Aerobic Maintenance Block
- Recovery Window
- Regeneration Quota

## Regeneration Product Flow

The `計畫` frontend surface provides a manual regeneration action.

When the athlete opens regeneration:

1. The frontend opens a thin settings sheet.
2. The sheet defaults to the current Active Projection's Race Strategy if that strategy still points to a future race.
3. If no current future Race Strategy exists, Johnny selects the default strategy by race priority and date.
4. The athlete may choose an explicit future race or choose maintenance even when future races exist.
5. The sheet does not preview the full generated plan.
6. If the athlete has exhausted today's Regeneration Quota, the sheet still opens, shows quota status and next availability, and disables confirmation.
7. If a training-plan generation run is already in flight, confirmation returns or displays the existing in-flight run instead of starting another.

Manual regeneration queues a backend product endpoint, not the raw agent-run endpoint. The product endpoint owns quota state, in-flight state, default strategy payloads, and user-facing availability.

## Regeneration Quota

V1 allows one successful manual Active Projection regeneration per athlete-local calendar day.

Rules:

- The calendar day uses Athlete Baseline timezone.
- If Athlete Baseline has no timezone, the server date is the fallback.
- Only a successfully created new Active Projection consumes quota.
- Attribute success to the athlete-local activation/completion day, even when the request was queued before midnight. Preserve the request day separately for request identity; retrying the same `client_request_id` still returns the same run.
- Failed runs, validation failures, queue failures, and in-flight returns do not consume quota.
- Background generation does not consume quota.
- This quota model must be implementation-ready for future paid-tier expansion.

## Race Strategy Selection

For automatic Race Strategy selection:

1. Select future races only.
2. Prioritize `primary`, then `secondary`, then `tune_up`.
3. If multiple races have the same priority, select the nearest race date.
4. A race with no target finish time still forms an explicit Race Strategy.
5. If a selected race has target finish time, plan around the race and stated goal.
6. If a selected race has no target finish time, use race distance to decide structure and Athlete Baseline to decide volume and targets. Johnny must not infer or invent a target finish goal.

If a race is more than 16 weeks away, Johnny creates a base or aerobic-development Plan Version for the first 16-week horizon toward that race strategy.

If the athlete chooses maintenance, or no useful future race exists, Johnny creates an Aerobic Maintenance Block.

## Projection Horizon And Dates

Manual regeneration:

- `starts_on` is tomorrow in the athlete's timezone.
- The projection does not modify today's workout.
- Race-based `ends_on` is the race date or the 16-week horizon end, whichever comes first.
- Maintenance `ends_on` is 4 weeks after `starts_on` minus one day.

Background generation:

- A Recovery Window begins on `previous.ends_on + 1`.
- The Recovery Window lasts seven full days.
- On the seventh Recovery Window day, Johnny may generate the next projection.
- The generated projection starts on the eighth day after the previous projection ended.
- For a delayed background retry, use the later of that eighth day and athlete-local tomorrow; never backdate the replacement projection.

## Background Generation

V1 uses a daily background check.

For each user, the background job checks whether the user needs a new Active Projection:

- If an Active Projection exists and has not ended, do nothing.
- If a previous projection ended fewer than seven full days ago, do nothing and let the Recovery Window continue.
- If the seventh Recovery Window day has arrived and no replacement projection exists, generate a new projection for the eighth day.
- If an explicit future Race Strategy exists, generate a race-based projection.
- Otherwise generate a 4-week Aerobic Maintenance Block.

The background job must be idempotent so repeated daily checks do not enqueue duplicate work.

## Plan Skeleton Ownership

Johnny creates the complete Plan Skeleton before LLM enrichment.

The skeleton owns:

- Workout dates.
- Weekly workout count.
- Long-run placement.
- Hard Session placement.
- Plan Phase assignment.
- Phase Segment coverage.
- The requested horizon.

The LLM receives the skeleton as a boundary. It may enrich:

- Workout purpose.
- Coach Note.
- Key-session Workout Steps.
- Repeat Blocks.
- Targets.
- Weekly rationale copy.

The LLM must not:

- Add weeks.
- Remove weeks.
- Move workout dates.
- Change workout count.
- Change phase coverage.
- Save partial plans.

ADR: `docs/adr/0001-deterministic-training-plan-skeletons.md`.

## Completeness Requirements

An Active Projection is complete only when all requirements pass:

- The plan covers the requested date horizon.
- Every week in the horizon has planned workouts.
- Weekly workout count follows Athlete Baseline.
- If Athlete Baseline has no explicit low-volume constraint, V1 defaults to at least 3 runs per week.
- If Athlete Baseline explicitly supports only 1-2 runs per week, Johnny respects that baseline.
- Every workout has a valid `phase`.
- Every workout date falls inside exactly one Phase Segment.
- Every workout's `phase` equals the matching Phase Segment phase.
- Every non-rest workout has planned duration or planned distance.
- Every key workout has structured Workout Steps sufficient for execution.

Rest days do not need stored workout entries.

## Hard Session Safety

V1 hard workout types:

- `interval`
- `tempo`
- `hill`
- `long_run`

Hard Session Capacity comes from Athlete Baseline:

- Field: `max_hard_sessions_per_week`.
- Default: `2`.
- V1 allowed range: `0..2`.
- Future advanced-tier support may allow `3`.
- The effective hard-session limit cannot exceed half of `max_runs_per_week`, rounded up, capped at `2`.
- Johnny may lower the effective limit based on injury status, recovery signals, or health context.
- Johnny's safety downgrade wins over the athlete's stated preference.

UI label:

- Use `質量課表`.
- Supporting copy should explain that it includes interval, tempo, hill, and long-run work.
- Avoid using `高強度` as the umbrella label because long runs are stressful without always being high intensity.

Hard Session scheduling rules:

- Each week has no more than the effective hard-session limit.
- Long run is a Hard Session.
- Hard Sessions should not be adjacent.
- Long run should not be adjacent to another Hard Session.

## Plan Phase And Metadata

V1 Plan Phase enum:

- `base`
- `build`
- `peak`
- `taper`
- `race`
- `maintenance`

The Plan Version stores canonical phase timeline metadata:

```json
{
  "phase_segments": [
    {
      "phase": "base",
      "starts_on": "2027-01-01",
      "ends_on": "2027-01-28",
      "focus": "Build aerobic consistency"
    }
  ]
}
```

Requirements:

- `metadata.phase_segments` is canonical.
- Phase Segment dates are inclusive.
- Phase Segments must fully cover `starts_on` through `ends_on`.
- Phase Segments must not overlap.
- Workouts must use a phase from the enum.
- `metadata.weekly_rationales` may explain coaching intent but is not canonical timeline data.
- Aerobic Maintenance Block uses a single `maintenance` phase in V1.

## Workout Structure

Workout names are deterministic Canonical Workout Names derived by Johnny from structured data. The LLM must not own canonical display names.

Every executable workout detail must be canonical structure:

- Workout Step.
- Repeat Block.
- Target.

Coach Note is optional supplemental guidance and is not executable structure.

Easy, recovery, and long runs may use a single `free_run` step or a simple warmup/main/cooldown structure.

Tempo, interval, hill, stride, and other key sessions must include:

- Warmup.
- Main work or repeat block.
- Recovery steps when appropriate.
- Cooldown.
- Targets expressed as pace, heart rate, or RPE.

Interval examples must expose:

- Repeat count.
- Work distance or duration.
- Target pace, HR, or RPE.
- Recovery distance or duration.
- Warmup and cooldown.

The frontend must be able to render the workout name, purpose, phase, coach note, compact summary, and full structured workout steps.

## Completion Repair

Johnny must validate generated output before persistence.

If LLM output is incomplete or invalid:

1. Attempt one repair pass.
2. If output remains incomplete, preserve valid generated weeks and perform deterministic Completion Repair for missing or invalid weeks.
3. Save only the fully repaired and validated projection.
4. Record repair details in agent run logs.
5. Record internal repair metadata.

Internal metadata shape:

```json
{
  "internal": {
    "completion_repair": {
      "repaired_week_indexes": [3, 4],
      "repaired_workout_ids": ["workout-1"],
      "reason": "LLM returned fewer weeks than requested"
    }
  }
}
```

The frontend ignores `metadata.internal`.

## Persistence And Transaction Rules

Saving a new Active Projection must be atomic:

1. Validate the full new projection.
2. Run Completion Repair if needed.
3. Re-validate the full repaired projection.
4. In one transaction, supersede conflicting old Active Projection records.
5. Persist the new Active Projection.
6. Record quota consumption only after the new Active Projection exists.

Failure before the transaction commits must leave the old Active Projection unchanged.

Historical workout completion on superseded plans must remain intact.

## Product API Requirements

Add product-level training plan regeneration APIs. The raw agent-run endpoint can remain for internal or developer use, but the frontend regeneration flow uses the product endpoint.

The product API must support:

- Fetching regeneration sheet defaults.
- Returning selected/default Race Strategy.
- Returning quota availability and next availability time.
- Returning in-flight run state.
- Starting regeneration with `client_request_id`.
- Returning the queued or existing run.

`client_request_id` prevents retries from creating duplicate runs. Daily quota prevents more than one successful manual regeneration per calendar day in V1.

If an in-flight generation exists, the start endpoint returns that run instead of queuing another.

## Frontend Requirements

The `計畫` page must expose regeneration without making the page feel like a draft-review workflow.

Thin sheet behavior:

- Opens from the Plan page.
- Shows the default selected Race Strategy.
- Lets the athlete choose a future race or maintenance.
- Shows quota state.
- Shows next available time when quota is exhausted.
- Disables confirmation when quota is exhausted.
- Returns existing in-flight state when generation is already running.
- Does not show full generated plan preview.

While generation runs:

- Keep showing the current Active Projection.
- Show generation-in-progress state.
- Switch to the new Active Projection only after generation succeeds and the training plan list refreshes.
- If generation fails, keep the old Active Projection visible.

Plan display:

- Uses `metadata.phase_segments` for the journey timeline.
- Displays workout phase on workout cards or detail surfaces where useful.
- Renders structured workout steps in the existing workout detail modal.
- Shows the seven inclusive days after an ended projection as a distinct Recovery Window, with dates and current recovery day. It is not a Plan Phase or an Active Projection. A covering replacement projection takes precedence.

## Athlete Baseline Requirements

Athlete Baseline adds:

- `max_hard_sessions_per_week`.

Validation:

- V1 accepts integers `0`, `1`, and `2`.
- Default is `2`.
- The effective limit is capped by weekly run count and safety context.

Frontend:

- Label: `質量課表`.
- Supporting copy mentions interval, tempo, hill, and long run.
- This setting should sit near training rhythm / max runs per week.

## Missing Or Weak Athlete Baseline

Johnny may generate when Athlete Baseline is incomplete.

Rules:

- If no race exists, generate a conservative Aerobic Maintenance Block.
- If a race exists, generate a conservative race-distance plan.
- Prefer RPE or low-confidence Targets when pace profile is weak.
- Do not infer a target finish time.
- Keep Hard Session Capacity conservative.

## Testing And Verification Requirements

Domain and application tests must verify:

- `hill` is accepted as a workout type.
- `max_hard_sessions_per_week` validates and round-trips through Athlete Baseline.
- Phase Segments fully cover plan dates and reject gaps or overlaps.
- Workouts must belong to exactly one Phase Segment.
- Workouts with mismatched phase are rejected or repaired.
- Manual regeneration starts tomorrow.
- Manual regeneration does not alter today's workout.
- New valid projection supersedes old Active Projection atomically.
- Failed generation leaves old Active Projection unchanged.
- Regeneration quota is consumed only after successful Active Projection creation.
- In-flight generation is reused instead of duplicated.
- Background generation respects Recovery Window timing.
- Background generation does not consume quota.
- Incomplete LLM output triggers repair and Completion Repair instead of saving partial projections.
- Completion Repair preserves valid weeks and fills invalid/missing weeks.
- Hard Session limit counts `interval`, `tempo`, `hill`, and `long_run`.
- Hard Session placement rejects adjacent hard days.

Frontend tests must verify:

- Regeneration sheet opens from `計畫`.
- Sheet shows default Race Strategy.
- Sheet allows maintenance selection even when races exist.
- Quota-exhausted state disables confirmation and shows next availability.
- In-flight state keeps current plan visible.
- Plan timeline renders from `metadata.phase_segments`.
- Workout detail renders structured steps.
- Athlete settings can edit `質量課表`.

## Out Of Scope

- Full generated-plan preview and approval flow.
- Paid-tier quota implementation beyond V1 daily quota structure.
- Advanced users choosing 3 hard sessions per week.
- LLM-owned full-calendar generation.
- Public Athlete Memory browsing.
- Race prediction or inferred finish-time goal generation.
- Multi-chunk LLM generation, unless single-pass enrichment remains unstable after V1.
