# Johnny

Johnny is an AI running companion context for training plans, workout execution detail, athlete baselines, and recommendation-safe plan changes.

## Language

**Workout Step**:
An executable segment of a planned workout, such as warmup, work, recovery, cooldown, drill, stride, hill, or free run.
_Avoid_: Step detail, workout instruction

**Repeat Block**:
A workout step that repeats a nested sequence of workout steps a fixed number of times.
_Avoid_: Interval group, repetition set

**Target**:
The intended effort for a workout step, expressed as pace, heart rate, or RPE.
_Avoid_: Intensity, prescription

**Target Evidence**:
The athlete-provided or matched activity evidence Johnny uses to derive optional numeric pace and heart-rate ranges after a workout is generated. Pace source and confidence describe the estimate independently of its primary effort target.
_Avoid_: Model pace guess, measured zone

**Pace Profile**:
Johnny's deterministic mapping from athlete baseline data to training pace zones used to enrich workout targets.
_Avoid_: LLM pace estimate, pace guess

**Athlete Baseline**:
The athlete's stated constraints, training preferences, injury context, weekly mileage, experience level, and recent baseline metrics that Johnny uses to personalize plans and recommendations.
_Avoid_: Profile settings, health stats, user config

**Capacity Snapshot**:
Johnny's dated estimate of current running volume and longest recent run, drawn from sufficient athlete-local activity history or marked as a low-confidence stated-mileage fallback.
_Avoid_: Experience score, proven inactivity, race readiness

**Coach Note**:
Optional LLM-authored guidance attached to a workout that is not canonical workout structure.
_Avoid_: Workout summary, instruction

**Canonical Workout Name**:
Johnny's deterministic display name for a workout, derived from its structured workout type, steps, repeat blocks, and targets.
_Avoid_: LLM workout title, catchy workout name

**Today Decision**:
Johnny's compact daily framing beside the canonical workout. Current requested Workout Advice may supply a short guidance line; absent or stale advice uses a conservative fallback. It does not itself approve a plan change.
_Avoid_: Daily status, readiness score, workout verdict

**Daily Review**:
The scheduled retrospective result published after 04:00 in the athlete's local time. It reviews yesterday and scores the seven completed local dates ending yesterday. Corrections revise only its own dated review; incomplete coverage or unresolved pairing withholds a score.
_Avoid_: Today's advice, readiness score, automatic workout adjustment

**Workout Advice**:
Guidance generated only from an athlete's request for today's workout, current activities, and optional structured constraints. A no-change answer remains useful guidance; a supported change is a separate Recommendation requiring approval. Its result and revision are independent of Daily Review.
_Avoid_: Scheduled review, conversation, direct workout edit

**Execution Score**:
A versioned, deterministic measure of completed prescribed sessions and volume alignment over seven completed local dates. It describes execution, not fitness, readiness, or injury risk. Unknown evidence produces a null score with a reason.
_Avoid_: Fitness score, missed workout inferred from failed sync

**Prescription Snapshot**:
An append-only record of the canonical workout that was effective when training occurred, including steps and Targets. It lets retrospective reviews survive plan replacement and later approved adjustments; uncertain legacy ordering is marked rather than guessed.
_Avoid_: Current display-only target estimate

**Legacy Daily Advice**:
The earlier combined Today coaching result, retained internally for transition reads. No new scheduled or sync-triggered producer writes it; the public Johnny surface uses Daily Review and Workout Advice instead.
_Avoid_: Daily Review, Workout Advice

**Plan Week**:
The owning Plan Version's seven-day block beginning at its start date plus whole seven-day intervals, truncated at the version end date. It is not a calendar Monday–Sunday week.
_Avoid_: Calendar week, rolling seven days

**Recommendation**:
A separate evidence-backed proposal. A Johnny workout adjustment links to a specific current Workout Advice revision and may only be accepted or rejected by its owner while the plan and evidence remain current; it cannot be edited into an unverified change.
_Avoid_: Daily Review, automatic plan change

**Signal Coverage**:
Johnny's view of which connected activity, recovery, health, and preference signals are available enough to support coaching recommendations.
_Avoid_: Provider status, sync dashboard, data completeness

**Race Strategy**:
The selected race context Johnny prepares for, including the target race and any athlete-stated race goal.
_Avoid_: Race selection, goal race, A race

**Supporting Race**:
A secondary or tune-up race inside the current plan horizon. A secondary race defaults to a full performance effort; a tune-up race defaults to a controlled training effort. Each occupies its event date in the Plan Skeleton, even when that date is outside preferred training days.
_Avoid_: Extra workout, optional event note

**Plan Series**:
A stable grouping of generated training plan versions that prepare for the same race strategy.
_Avoid_: Race plan, plan group

**Plan Version**:
A generated projection within a plan series that supersedes or continues earlier projections while preserving history.
_Avoid_: Replacement plan, regenerated plan

**Active Projection**:
The current plan version used as the default source for future planned workouts.
_Avoid_: Current calendar, active plan

**Plan Phase**:
A coaching segment within a plan version, such as base, build, peak, taper, race, or maintenance.
_Avoid_: Plan stage, UI phase, calendar section

**Phase Segment**:
A dated span in a plan version that assigns one plan phase to a range of training days.
_Avoid_: Timeline item, phase card, weekly rationale

**Plan Skeleton**:
Johnny's deterministic dates, phases, workout types, and prescribed durations for a plan version before workout details are enriched.
_Avoid_: LLM outline, rough plan, empty template

**Workload Prescription**:
The versioned weekly running-minute, long-run, and terrain-session targets Johnny computes from a Capacity Snapshot, Race Strategy, and Athlete Baseline constraints before building a Plan Skeleton.
_Avoid_: LLM workload, race-distance multiplier

**Preparation Assessment**:
Johnny's comparison of a feasible Plan Version against a calibrated race-planning reference, with `on_track`, `gap`, or `unknown` status and named factors. It does not predict completion or grant medical clearance.
_Avoid_: Readiness guarantee, safety clearance

**Hard Session**:
A workout that meaningfully stresses the athlete, such as interval, tempo, hill, race-pace, or long run.
_Avoid_: Key workout, intense day, difficult workout

**Hard Session Capacity**:
The athlete's stated upper bound for weekly hard sessions before Johnny applies safety downgrades from injury or recovery context.
_Avoid_: Intensity preference, workout difficulty setting, quality workout quota

**Completion Repair**:
Johnny's deterministic process for filling missing or invalid weeks in a generated plan version before it can become the active projection.
_Avoid_: Partial fallback, silent patch, best-effort save

**Aerobic Maintenance Block**:
A generated plan version focused on preserving general running fitness when Johnny is not preparing for a near-term race strategy.
_Avoid_: No-race plan, filler plan, base plan

**Recovery Window**:
A deliberate gap after a plan version ends where Johnny does not immediately start the next active projection.
_Avoid_: Empty plan, missing plan, inactive week

**Regeneration Quota**:
The user's allowed number of manual active projection regenerations in a product-defined time window.
_Avoid_: Retry limit, rate limit, daily cap

**Athlete Memory**:
Johnny's private long-term understanding of an athlete's habits, preferences, injury history, adaptation patterns, and responses to prior training decisions.
_Avoid_: Training log, coach notes, activity history
