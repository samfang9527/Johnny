## Why

The existing duration formula starts with reported weekly mileage, treats intermediate and advanced identically, limits race growth to 10% above the starting budget, caps long runs at 120 minutes, and treats every race longer than a half marathon alike. Recent completed activities are passed to the model but do not determine the skeleton's workload. Thus prompt changes alone cannot produce a substantially more appropriate 40 km trail Plan Version.

## What Changes

- Derive a typed capacity snapshot from recent running activities and the Athlete Baseline, with explicit source and confidence.
- Extend Race Strategy data with optional course ascent, descent, terrain, cutoff, and goal intent; leave existing Race Goals valid.
- Introduce a versioned deterministic workload policy that produces weekly workload budgets, long-run progression, phase intent, and a preparation assessment before building the Plan Skeleton.
- Validate model Workout Steps against both the skeleton's upper bounds and required executable content. Completion Repair must preserve the workload policy's scheduled durations.
- Persist policy version, assumptions, evidence, and preparation assessment in internal plan metadata and expose a concise athlete-facing assessment in the Plan view.
- Test the original 40 km symptom, supported higher-capacity athletes, incomplete data, short horizons, injury constraints, and local/OpenAI repair paths.

## Capabilities

- `athlete-race-domain`: optional structured course and goal fields.
- `training-plan-domain`: capacity, workload progression, and preparation assessment semantics.
- `agent-runtime-tools`: preload, prompt, validation, and repair of policy-backed skeletons.
- `backend-api`: compatible race and plan response fields.
- `frontend-today-visual-design`: race input and plan assessment presentation.

## Scope And Compatibility

This change does not alter direct manual training-plan CRUD, the daily Today Decision, Regeneration Quota, or the 16-week maximum Plan Version horizon. Old Race Goals and Plan Versions remain readable. The existing race `metadata_json` and plan `metadata_json` can hold the new fields; no new table is proposed. Course metrics must never be inferred from a race name.

## Existing Decision Conflict

The older detailed-workout-steps change says the LLM owns weekly structure and workout selection. The later training-plan-generation spec and ADR-0001 assign those to Johnny's deterministic Plan Skeleton. This change follows the later decision and updates active specs if approved.
