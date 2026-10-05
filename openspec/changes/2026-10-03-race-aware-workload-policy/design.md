# Design: Race-aware workload policy

## Intent and boundary

The user-reported failure is a 40 km trail Plan Version made of roughly 30-minute ordinary runs and a roughly 69-minute longest long run, with little change after switching experience from beginner to advanced. Johnny currently owns the Plan Skeleton, and `createTrainingPlan` requires exact agreement with its workouts. This design changes the deterministic prescription before model enrichment. It retains ADR-0001's ownership of dates, workout types, phases, and completeness.

Success means that a Plan Version (1) starts from recorded or explicitly stated capacity, (2) progresses across the available horizon where constraints permit, (3) differentiates race demands including known terrain, and (4) names a preparation gap when the scheduled load cannot meet the policy's reference. No status promises race completion.

## Data and trust model

`CapacitySnapshot` is computed in application/domain code before model invocation. Query all user-scoped activities for the preceding 56 days; do not use the current 28-day, 20-record model-context slice as the policy input. Include only normalized running sports (`run`, `running`, `trail_run`, and the provider's verified running variants), deduplicate by persisted activity ID, and group into athlete-local calendar weeks. Preserve source IDs internally for audit. Ignore non-running activities for running workload; their presence does not fill missing running history.

For a high-confidence activity baseline, require at least eight completed runs across the latest four complete calendar weeks, with at least two runs in three of those weeks and at least one run in the last 14 days. Use median weekly running minutes across those four calendar weeks, total distance as a separate metric, and the longest run in the past 28 days. These are proposed **data sufficiency rules**, not injury thresholds. If they fail, use `AthleteProfile.current_weekly_mileage_km` as a low-confidence weekly estimate using the existing six-minutes-per-km accounting conversion. When stated mileage is zero or missing, use the conservative current defaults, mark confidence low, and never treat absent synced activities as proven inactivity. The actual activity snapshot takes precedence over the experience label and stated mileage when it is sufficient. The selected source, window, sample count, and missing dimensions are persisted in internal plan metadata.

`RaceDemand` uses distance, date, optional target finish, optional ascent/descent, `terrain_difficulty` (`runnable`, `mixed`, `technical`, or null), `cutoff_seconds` (positive or null), and `goal_intent` (`complete`, `perform`, or null). Course values are explicitly entered by the athlete and may be unknown. They are stored in the existing Race Goal metadata JSON and exposed through the existing race API. Do not parse terrain from a free-text name. Descent is captured for planning context; V1 activity data only measures ascent, so Johnny cannot claim measured downhill preparation.

The frontend offers those course inputs as optional fields in the existing Race Goal modal. Legacy races remain null for all new fields. Generated plans store a compact public `preparation_assessment` separate from detailed private policy evidence. The Plan view displays the status and concrete reasons near the Race Strategy. Existing/manual plans without this field display their ordinary plan view.

## Deterministic policy

Introduce a pure `build_workload_prescription(capacity, race_demand, constraints, window, prior_plan)` function returning weekly `WorkloadWeek` records plus `PreparationAssessment`. `build_plan_skeleton` consumes this result to assign dated workouts and durations. The policy has a version string; every generated plan records the exact version. Existing hard-session spacing, weekly run limits, injury downgrade, and phase coverage remain hard constraints. Do not silently expand `max_runs_per_week` or disregard selected days to meet a race reference.

The proposed V1 progression rule is a **reviewable product heuristic**, not a universal training rule:

1. Initial weekly running minutes equal the activity baseline when high confidence. With a stated-mileage fallback, start at no more than that estimate. Missing/zero baseline retains 20-minute ordinary runs and 30-minute long runs until evidence is available; the assessment is `unknown` or `gap`, never `on_track`.
2. Across development weeks, target weekly minutes increase by at most 5% from the previous development high. Every fourth week is a cutback at 85% of the preceding development target; the next development week resumes from that high rather than compounding from the cutback. Taper reduces volume ahead of a race. Partial weeks are prorated by available scheduled days.
3. The long run increases by at most 10% over the longest completed or previously prescribed long run in the preceding four weeks, and takes no more than 50% of that week's minutes. The V1 absolute long-run ceiling is 180 minutes for races of 30–50 km; other race bands retain or receive separately reviewed ceilings. If these bounds conflict, take the lower value and report the limiting factor.
4. The existing quality-session eligibility, Hard Session Capacity, injury downgrade, and spacing constraints apply after the workload budget is set. Experience may change eligible session complexity, but intermediate versus advanced alone cannot create a higher starting budget. `current` or `recent` injury prevents aggressive build; the policy keeps or reduces load and records the constraint.
5. Maintenance and a race beyond the 16-week horizon remain aerobic development. They retain the same capacity and progression checks, without claiming this Plan Version completes race preparation.

**Proposed preparation reference for product review:** for a 30–50 km race, the peak pre-taper plan should include at least 300 weekly running minutes and a 150-minute long run; for a race over 50 km, the reference is higher and must be calibrated before enabling an `on_track` result. For known `mixed` or `technical` terrain, two specific trail/hill exposures in the final eight development weeks are required for the terrain dimension. Known ascent requires an ascent-specific plan objective and evidence; V1 does not convert meters climbed to flat-road minutes. A preparation reference is an internal comparison point, not a claim that these numbers are sufficient or safe for an individual athlete. Coaching review of these figures is a required design decision before code implementation. Until a band is calibrated, its status is `unknown`, never `on_track`.

Compute `on_track` only when every applicable, calibrated reference is met and the baseline has sufficient confidence. Compute `gap` when a measured or prescribed dimension falls short. Compute `unknown` for an uncalibrated band or a dimension lacking required evidence; a known gap takes precedence over unknowns. Store factors such as `long_run_endurance`, `weekly_volume`, `terrain_exposure`, `limited_days`, `short_horizon`, and `missing_baseline`, with short Traditional Chinese explanations. The status is a preparation assessment, not a race prediction or medical clearance.

The 40 km / 25 km-week / three-days example should now produce a progressive skeleton where training history and time permit, and it should carry a gap if the 150-minute/300-minute reference cannot be reached within the 16-week window. Raising experience alone cannot force the assessment to `on_track`. A demonstrably higher-capacity athlete can receive longer long runs within the approved policy. Race distance above 50 km must not reuse the 40 km readiness reference unchanged.

## Generation and activation path

1. Manual or scheduled regeneration queues the existing workflow. Provider/model choice remains pinned at queue time.
2. The worker loads Athlete Baseline, selected Race Strategy, full 56-day activity window, previous Plan Version, and constraints. Failure to read optional activity data is recorded as missing evidence; race/profile access failure still fails generation rather than inventing inputs.
3. The pure policy returns capacity, race demands, weekly prescription, and preparation assessment. The skeleton builder assigns dates, phases, types, and exact durations from that prescription.
4. Model context includes a compact policy summary, skeleton, gap factors, and instructions to write Coach Notes and Workout Steps that match the prescription. `createTrainingPlan` receives trusted policy context separately from untrusted model arguments. Local generation uses the same policy.
5. Validation requires exact skeleton dates, phases, types, and durations and checks executable steps against both upper and lower duration consistency bounds. The lower bound is 90% of planned time for duration-based workouts, allowing rounding and warmup structure; distance-only steps use the existing conservative conversion for accounting. One model repair attempt may correct invalid steps. Completion Repair and fallback template steps fill the prescribed duration, retain the preparation assessment, and record repair provenance.
6. In one transaction, a fully validated new Active Projection supersedes the previous one. Plan metadata includes `workload_policy_version`, public `preparation_assessment`, and private source/repair details. The API returns the public assessment with plan data. The frontend shows it after the existing poll/refresh flow.

## Interfaces and files

- New `backend/src/application/training_workload_policy.py`: typed capacity, race demand, constraints, weekly prescription, assessment, and pure policy functions. The training-plan generator consumes it; the LLM gateway does not import it.
- `backend/src/application/agent_runtime.py`: full activity preload, policy invocation, trusted context, and revised prompt. Keep the 20-record slice only for model context.
- `backend/src/application/training_plan_generation.py`: assign skeleton durations from the weekly prescription; remove the original fixed duration formula for generated race plans.
- `backend/src/application/agent_tools.py` and local/OpenAI gateways: policy-aware validation, repair, metadata, and step-detail contract.
- `backend/src/domain/athlete_race.py`, database race mapping, API race schemas/routes: optional Race Goal fields; no table migration because race metadata JSON already exists.
- Training-plan API schemas and frontend types, `RaceGoalModal.vue`, and Plan view: course inputs and public assessment.
- Tests: pure policy unit cases, API/repository round trips, model/local validation and repair, frontend display, and the exact 40 km differential reproduction.

## Failure and compatibility behavior

Legacy Race Goals with null course fields use distance-only planning and show unknown course dimensions. Legacy or manually created plans without policy metadata remain readable. A missing activity feed produces low confidence; it does not silently return `on_track`. Model failure uses policy-aligned templates; a policy calculation or race/profile data error fails the run before activation and leaves the previous Active Projection intact. A regenerated Plan Version does not rewrite completed, skipped, or adjusted workout history.

## Design review decisions

The numeric progression and 30–50 km preparation reference above are provisional, versioned product defaults. The product owner approved implementation on 2026-10-05; coaching review must confirm or change these values before release. Approval also confirms that an honest `gap` or `unknown` assessment is acceptable even when a complete Plan Version is generated, and that the optional course fields belong on Race Goal rather than a separate course entity.

Implementation starts only after the product owner approves this `design.md`, as required by `openspec/AGENTS.md` and `openspec/project.md`.
