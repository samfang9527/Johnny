# Detailed Workout Steps

Generated training plans should include step-level workout structure for key sessions instead of only high-level purpose, duration, distance, and pace fields. Interval, tempo, and threshold-style workouts need enough detail to tell the athlete what to do: warmup, repeat blocks, recoveries, cooldown, and target effort.

The LLM owns coaching logic, workout selection, workout intent, and optional coach notes. Johnny owns canonical summary rendering, pace/heart-rate/RPE enrichment, validation, fallback templates, and persistence safety.

V1 stores structured workout steps in existing workout details JSON, adds plan metadata for race-plan version continuity, exposes step details through existing training plan responses, and renders compact workout previews plus a detail modal in the frontend.
