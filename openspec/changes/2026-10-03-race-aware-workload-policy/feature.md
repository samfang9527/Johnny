# Race-aware training workload

Johnny currently fixes workout dates, types, and durations before asking the LLM to enrich a Plan Version. In a reproducible 16-week example for a 40 km race and an athlete reporting 25 km/week, intermediate and advanced produce the same Plan Skeleton and the longest long run is 70 minutes. A 100 km race also produces the same skeleton as a 40 km race at that baseline. The model cannot correct those outputs because `createTrainingPlan` enforces the skeleton.

The intended result is an Active Projection that progresses from the athlete's current demonstrated capacity toward the selected Race Strategy, uses course demands when known, and explains any material preparation gap. Experience level informs interpretation and workout complexity; it does not substitute for current training history. A completed plan is not presented as proof of race readiness.

This change keeps Johnny's deterministic ownership of the Plan Skeleton (ADR-0001), complete Plan Versions, existing regeneration quota, and one-repair-then-completion-repair behavior. It changes the workload policy, the context and contract supplied to the LLM, and the information shown with the resulting plan.

This is a proposed product policy for review. Numerical training and readiness thresholds in `design.md` are product heuristics requiring coaching review before implementation; they are not medical or completion guarantees.
