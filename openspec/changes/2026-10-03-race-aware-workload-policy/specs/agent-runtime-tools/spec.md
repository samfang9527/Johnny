## MODIFIED Requirements

### Requirement: Training Plan Generation Workflow
The system SHALL preload a capacity snapshot, Race Strategy demands, versioned workload prescription, and preparation assessment alongside the Plan Skeleton. The model SHALL enrich Workout Steps, purposes, and Coach Notes within the prescribed dates, types, and durations.

#### Scenario: Model proposes a longer workout
- **GIVEN** a skeleton workout has a prescribed duration
- **WHEN** `createTrainingPlan` receives a longer duration or executable steps exceeding that prescription
- **THEN** validation rejects that workout for one model repair attempt
- **AND** Completion Repair uses the prescribed duration if the model still fails

#### Scenario: Model omits executable workload
- **GIVEN** a skeleton workout has a prescribed duration
- **WHEN** model steps cover materially less than the workout's planned duration
- **THEN** validation requests repair or uses policy-aligned template steps
- **AND** the persisted Workout Steps remain consistent with the athlete-facing planned duration

#### Scenario: Local deterministic generation
- **WHEN** a queued plan uses the local provider
- **THEN** its workouts and preparation assessment reflect the same policy-backed Plan Skeleton as an OpenAI run

#### Scenario: Generation observability
- **WHEN** a Plan Version is saved after model output, repair, or fallback
- **THEN** internal metadata records the policy version, input provenance, and any repair/fallback reason
- **AND** the run remains identifiable as local, model-enriched, or repaired
