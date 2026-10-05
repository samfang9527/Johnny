## ADDED Requirements

### Requirement: Capacity Snapshot
The system SHALL derive an auditable starting capacity from running activity history and the Athlete Baseline before building a generated Plan Skeleton.

#### Scenario: Sufficient recent history
- **GIVEN** the latest four complete calendar weeks contain at least eight completed runs, at least three of those weeks contain two or more runs, and at least one run occurred in the last 14 days
- **WHEN** generation begins
- **THEN** the snapshot uses completed running duration, distance, longest run, and available ascent evidence as its primary source
- **AND** it records the observation window, source, and confidence

#### Scenario: Sparse or missing history
- **GIVEN** activity coverage does not meet the sufficient-history rule
- **WHEN** generation begins
- **THEN** the snapshot uses the athlete's stated current weekly mileage conservatively and marks capacity confidence as low
- **AND** missing activity is not interpreted as proof that the athlete did no training

### Requirement: Workload Prescription
The system SHALL create a deterministic, versioned weekly workload prescription before model enrichment. The prescription SHALL respect training-day capacity, injury constraints, and progression from the capacity snapshot, while recording the selected Race Strategy's demands separately from what can be scheduled.

#### Scenario: Longer race with time to prepare
- **GIVEN** an established athlete, a 40 km trail Race Strategy, and a 16-week horizon
- **WHEN** Johnny builds the Plan Skeleton
- **THEN** base, build, peak, and taper have distinct workload intent
- **AND** long-run and weekly workloads can progress beyond the previous fixed 10% total-growth and 120-minute-long-run limits when the approved policy permits it

#### Scenario: Same history with a different experience label
- **GIVEN** two otherwise identical Athlete Baselines and completed histories differing only in intermediate versus advanced experience level
- **WHEN** Johnny prescribes workload
- **THEN** the experience label alone does not create a larger starting workload or bypass progression constraints
- **AND** eligible workout complexity may differ within the same workload bounds

#### Scenario: Short horizon or limited training capacity
- **GIVEN** the Race Strategy demands exceed what can be built from current capacity within the available weeks and training days
- **WHEN** Johnny produces a Plan Version
- **THEN** it keeps the scheduled workload within the policy's bounds
- **AND** records a material preparation gap rather than increasing sessions to satisfy the race target

#### Scenario: Continuation of a Plan Series
- **GIVEN** a prior Plan Version and newer completed training
- **WHEN** Johnny generates the next Active Projection
- **THEN** its starting capacity uses recent evidence and continuity context
- **AND** completed, skipped, and adjusted historical workouts remain intact

### Requirement: Preparation Assessment
Every generated race Plan Version SHALL include an assessment with `on_track`, `gap`, or `unknown` status, named contributing factors, and policy version. `on_track` means the policy's preparation reference is met; it SHALL NOT imply guaranteed completion or medical clearance.

#### Scenario: Unavailable course or capacity evidence
- **WHEN** the inputs required for a confident assessment are missing
- **THEN** the assessment is `unknown` for those dimensions and names the missing information

#### Scenario: 40 km plan with a short attainable long run
- **GIVEN** a 40 km Race Strategy and a feasible peak long run below the approved preparation reference
- **WHEN** the plan is generated
- **THEN** the assessment is `gap` and identifies long-run endurance as a contributing factor
