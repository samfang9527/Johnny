## Design

### Agent Flow

`training_plan_generation` exposes only `createTrainingPlan` as its write tool. The prompt asks for a validated active training plan and explicitly says not to create recommendations in this workflow. Runtime completion requires a `training_plan` payload, not a recommendation.

### Tool Contract

`CreateTrainingPlanTool` builds a `TrainingPlan` with `status="active"` and calls `TrainingPlanStore.create_active_plan`. The tool returns `{"training_plan": ..., "applied": true}`.

### Persistence

`SqlAlchemyTrainingPlanRepository.create_active_plan` validates active status, persists the new plan, and marks existing active plans as `superseded` only when they belong to the same user, target the same non-null race, and overlap the new plan's date range.

### Recommendation Approval

Recommendation domain validation supports only workout adjustments, recovery warnings, and informational recommendations. Proposed actions support only `adjust_workout` and `no_plan_change`. Accepting a recommendation no longer activates a draft training plan.

### Gateways

The local gateway emits one deterministic `createTrainingPlan` call for `training_plan_generation`. The OpenAI gateway exposes a strict `createTrainingPlan` schema and rejects old `training_plan_creation` recommendation payloads.
