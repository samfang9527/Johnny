## Design

### Domain Language

A **workout step** is an executable segment of a workout. A **repeat block** is a step that repeats nested workout steps. A **target** is the intended effort for a step, represented as pace, heart rate, or RPE. A **pace profile** is Johnny's deterministic mapping from athlete baseline data to training pace zones. A **plan series** groups versions of a race-preparation plan.

### Workout Step Contract

Workout details JSON stores:

```json
{
  "purpose": "Improve 5K-specific aerobic power",
  "planned_distance_meters": 8600,
  "pace_range_seconds_per_km": [275, 285],
  "heart_rate_zone": "Z4",
  "phase": "build",
  "coach_note": "Keep the first two reps controlled.",
  "steps": [
    {
      "type": "warmup",
      "duration_seconds": 900,
      "target": { "kind": "rpe", "rpe": 3 }
    },
    {
      "type": "repeat",
      "repeat_count": 4,
      "steps": [
        {
          "type": "work",
          "distance_meters": 800,
          "target": {
            "kind": "pace",
            "zone": "interval",
            "pace_range_seconds_per_km": [275, 285],
            "rpe": 8
          }
        },
        {
          "type": "recovery",
          "distance_meters": 400,
          "target": { "kind": "pace", "zone": "easy", "rpe": 3 }
        }
      ]
    },
    {
      "type": "cooldown",
      "duration_seconds": 600,
      "target": { "kind": "rpe", "rpe": 2 }
    }
  ]
}
```

Supported step types are `warmup`, `work`, `recovery`, `cooldown`, `repeat`, `drill`, `stride`, `hill`, and `free_run`. Non-repeat steps require `duration_seconds` or `distance_meters`. Repeat steps require `repeat_count >= 1` and at least one nested step. `hill` steps may include `grade_notes`. All non-repeat steps may include `notes`.

Targets support:

- `pace`: requires `zone`; may include computed `pace_range_seconds_per_km`, `rpe`, and `confidence`.
- `heart_rate`: requires `heart_rate_zone`; may include `heart_rate_range_bpm`, `rpe`, and `confidence`.
- `rpe`: requires integer `rpe` from 1 through 10.

Allowed pace zones are `easy`, `steady`, `marathon`, `threshold`, `interval`, `repetition`, and `rpe_only`.

### Summary Ownership

The app renders canonical summaries from structured steps. V1 compact format is:

```text
15 min warmup + 4 x (800m interval / 400m easy) + 10 min cooldown
```

The LLM may write `coach_note`, but the note is optional, limited to 500 characters, and not used as canonical workout content.

### Pace Profile

The application builds an athlete pace profile before generation and enrichment. V1 sources are:

- Threshold pace in `AthleteProfile.training_preferences` JSON with high confidence.
- Race target pace from selected race goal as low-confidence fallback.
- Recent activity average pace as low-confidence fallback.

High and medium confidence profiles may produce pace ranges. Low-confidence profiles produce RPE-only targets. The pace profile includes source and confidence metadata so generated plans can explain why exact paces are or are not shown.

### Agent Flow

The training-plan generation request preloads athlete profile, baseline, races, recent activity summary, limited raw key sessions, current or last active plan, and deterministic pace profile. The LLM may call read tools for extra information, then must call `createTrainingPlan`.

The LLM chooses plan logic, phases, weekly structure, workout types, step layout, target zones, and coach notes. `createTrainingPlan` computes and stores target snapshots using the pace profile, validates structures and totals, and persists the active plan.

Invalid generated plans are repaired once. If the repaired output is invalid, the application creates an athlete-adjusted deterministic fallback plan rather than returning no usable plan.

### Plan Continuity

Generated race plans keep continuity metadata in `training_plans.metadata_json`:

```json
{
  "plan_series_id": "series-uuid",
  "previous_plan_id": "plan-uuid",
  "version": 3,
  "generation_mode": "full_initial|rolling_projection",
  "continuity_summary": "Continue build phase with threshold volume progression.",
  "weekly_rationales": [
    {
      "week_index": 3,
      "phase": "build",
      "focus": "Extend threshold volume while keeping long run steady",
      "load_progression": "Increase volume about 6% from previous week",
      "key_workouts": ["tempo", "long_run"]
    }
  ]
}
```

V1 uses latest active projection by default and keeps old versions available through plan history. Rolling generation creates a new full projection from today through race day, preserving completed, skipped, and manually adjusted history. V1 may supersede active plans, but it must carry `plan_series_id`, `previous_plan_id`, and continuity summary when creating a new version.

### API And Frontend

Existing training plan responses expose plan metadata and workout details, including steps, phase, coach note, and compact summary. Manual training plan requests may include structured steps, though V1 frontend editing remains view-only.

The Today card shows a compact deterministic step summary when available. A workout detail modal shows the full step structure and optional coach note. Simple legacy workouts without persisted steps get synthetic display-only `free_run` steps at read/render time without mutating stored rows.

## Approval Gate

Implementation must not start until the product owner approves this `design.md`.
