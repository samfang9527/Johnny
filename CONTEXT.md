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

**Pace Profile**:
Johnny's deterministic mapping from athlete baseline data to training pace zones used to enrich workout targets.
_Avoid_: LLM pace estimate, pace guess

**Coach Note**:
Optional LLM-authored guidance attached to a workout that is not canonical workout structure.
_Avoid_: Workout summary, instruction

**Plan Series**:
A stable grouping of generated training plan versions that prepare for the same race strategy.
_Avoid_: Race plan, plan group

**Plan Version**:
A generated projection within a plan series that supersedes or continues earlier projections while preserving history.
_Avoid_: Replacement plan, regenerated plan

**Active Projection**:
The current plan version used as the default source for future planned workouts.
_Avoid_: Current calendar, active plan
