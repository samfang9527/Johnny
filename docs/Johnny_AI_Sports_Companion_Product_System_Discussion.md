# Johnny AI Sports Companion - Product and System Discussion

## Purpose of This Document

This document summarizes what I understand from `Johnny_AI_Sports_Companion_Project_Concept.md`, expands the possible feature set, and proposes an initial product and technical direction for discussion.

This is not an implementation plan. It is a shared product/system design draft to align on scope before writing code.

## Update: MVP OpenSpec Decomposition

The MVP has been decomposed into OpenSpec-compatible change folders under `openspec/changes/`.

Each feature folder contains:

- `feature.md`: human-readable feature scope, order, dependencies, non-goals, and testable outcome
- `proposal.md`: OpenSpec proposal for why and what changes
- `specs/<capability>/spec.md`: OpenSpec delta requirements and scenarios
- `design.md`: technical design to discuss before implementation
- `tasks.md`: small, testable implementation checklist

Every `tasks.md` starts with a design review gate:

```text
Design review gate: discuss design.md and receive explicit approval before implementation.
```

This enforces the rule that no feature implementation starts until its design has been discussed and approved.

### Bottom-Up MVP Order

| Order | Change | Layer | Result |
| --- | --- | --- | --- |
| 1 | `openspec/changes/01-project-foundation/` | Tech stack | Vue/Vite frontend, PostgreSQL database config, local dev, test, and health-check foundation |
| 2 | `openspec/changes/02-persistence-schema/` | Database schema | PostgreSQL schema, migrations, repository boundary |
| 3 | `openspec/changes/03-athlete-race-domain/` | Domain model | Athlete profile, preferences, race goal, target pace |
| 4 | `openspec/changes/04-training-plan-domain/` | Domain model | Training plan, workouts, statuses, adjustment proposals |
| 5 | `openspec/changes/05-activity-health-domain/` | Domain model | Activities, health metrics, manual data entry, workout matching |
| 6 | `openspec/changes/06-training-analytics/` | Core business logic | Deterministic metrics, recovery context, Today context |
| 7 | `openspec/changes/07-recommendation-approval/` | Core business logic | Evidence-backed recommendations and user approval workflow |
| 8 | `openspec/changes/08-agent-runtime-tools/` | Agent application layer | Single Running Companion Agent, domain tools, observability |
| 9 | `openspec/changes/09-integrations-notifications/` | Infrastructure and async workflows | Activity provider ingestion and LINE notification boundary |
| 10 | `openspec/changes/10-backend-api/` | API/BFF | MVP route contracts for frontend and webhooks |
| 11 | `openspec/changes/11-frontend-today-calendar/` | Frontend | Today page, recommendation actions, training calendar |
| 12 | `openspec/changes/12-frontend-conversation-inbox/` | Frontend | AI coach conversation and Agent Inbox |

OpenSpec project-level context was also added:

- `openspec/project.md`
- `openspec/AGENTS.md`

The resulting MVP development flow is:

```text
Pick next numbered change
  -> Read feature.md
  -> Discuss and approve design.md
  -> Review proposal.md and specs
  -> Implement tasks.md step by step
  -> Verify tests
  -> Archive/update specs when complete
```

---

## 1. What I Understand

Johnny is an AI running companion, not a generic chatbot and not only a training-plan generator.

The core product idea is a long-term companion loop:

```text
Observe -> Understand -> Reason -> Recommend -> User Decision -> Act -> Learn
```

Johnny should gradually understand the athlete behind the data:

- Race goals and training timeline
- Current training plan
- Recent running activities
- Sleep, HRV, resting heart rate, and recovery signals
- Training load and fatigue trends
- Subjective feedback such as soreness, motivation, stress, pain, or schedule changes
- Preferences such as preferred training days, disliked workouts, max weekly running days, treadmill preference, and preferred interval formats
- Long-term adaptation patterns, for example needing more recovery after intervals

The intended user experience is:

> Johnny feels like a running friend who knows my training history, current state, and goals, then gives useful suggestions with evidence.

Important product principles:

- AI should recommend, explain, and assist, but not silently make major training changes.
- The UI should show evidence, not only AI conclusions.
- Core training and recovery metrics should be deterministic, not invented by the LLM.
- The agent should use domain tools instead of direct database access.
- The first version should focus on the training loop, not broad content/news/race discovery.
- Johnny should eventually support proactive recommendations through event-driven and scheduled analysis.

---

## 2. Product Surfaces

The concept proposes three primary interaction surfaces.

### 2.1 Today

The daily home surface.

Purpose:

- Show the user's current training context at a glance.
- Answer "What should I do today?"
- Make AI recommendations explainable and actionable.

Likely content:

- Next race and countdown
- Race goal
- Today's planned workout
- Recovery status
- Sleep summary
- HRV trend
- Resting heart rate trend
- Recent training load
- Yesterday's workout summary
- Johnny's recommendation
- Evidence behind recommendation
- Actions: start workout, adjust workout, rest, ask why, discuss

### 2.2 Conversation

The flexible reasoning surface.

Purpose:

- Handle ambiguous, contextual questions that do not fit into fixed UI.
- Let users ask for analysis, explanations, adjustments, and strategy.

Examples:

- "My legs are sore but not painful. Should I run today?"
- "I need to hike next Saturday. Can you adjust my plan?"
- "Why did my heart rate drift in recent long runs?"
- "Can you build a race strategy for my marathon?"

Important architecture point:

- The LLM should not own all user data.
- The LLM should call domain tools such as `getTrainingPlan`, `getRecentActivities`, `getRecoveryState`, and `calculateTrainingLoad`.

### 2.3 Agent Inbox

The proactive recommendation surface.

Purpose:

- Hold suggestions generated by scheduled jobs, data events, and agent analysis.
- Let users approve, reject, edit, or discuss recommendations.

Examples:

- Recovery warnings
- Training adjustment suggestions
- Weekly training reviews
- Race strategy reminders
- Progress insights
- Future content/news/equipment recommendations

---

## 3. Feature Inventory

This section lists possible features implied by the concept. Not all should be MVP.

### 3.1 Account and Athlete Profile

- User sign-up/sign-in
- Athlete profile
- Running experience level
- Current weekly mileage
- Historical peak mileage
- Preferred training days
- Max training days per week
- Preferred long-run day
- Workout preferences
- Injury history
- Fatigue sensitivity
- Time availability
- Location/timezone
- Units: metric/imperial
- Privacy/data permissions

### 3.2 Race Goal Management

- Create race
- Race date
- Race distance
- Target finish time
- Target pace
- Training period
- Priority race vs tune-up race
- Race course profile
- Elevation profile
- Aid station data
- Race-day weather
- Race strategy generation
- Race checklist
- Fuel and hydration strategy

### 3.3 Training Plan

- Generate initial plan from race goal and athlete profile
- Training calendar
- Workout types: easy, recovery, long run, tempo, threshold, interval, strides, rest, cross-training
- Planned distance/duration
- Planned pace range
- Planned heart-rate zone
- Workout purpose
- Workout status: planned, completed, skipped, adjusted
- Manual workout edits
- Agent-suggested workout edits
- Plan version history
- Adjustment reason history

### 3.4 Data Integration

- Garmin activity sync
- Garmin health/recovery sync
- Strava activity sync
- Apple Health through future iOS companion app
- Webhook ingestion
- Manual activity entry for MVP fallback
- Data source connection status
- Sync history
- Duplicate detection
- Data normalization across providers

### 3.5 Activity and Health Data

- Running activities
- Distance
- Duration
- Pace
- Splits
- Heart rate
- Elevation
- Training load
- Cadence, if available
- Sleep duration
- Sleep quality
- HRV
- HRV baseline
- Resting heart rate
- Recovery score
- Stress score, if available
- Subjective readiness
- Subjective soreness
- Pain flags

### 3.6 Deterministic Analytics

The following should be computed by application code, not by the LLM:

- Weekly mileage
- Previous weekly mileage
- Mileage ramp rate
- Acute load
- Chronic load
- Acute:chronic workload ratio
- Training monotony
- Training strain
- Recovery score
- HRV delta from baseline
- Resting HR delta from baseline
- Sleep debt
- Pace zones
- Heart-rate zones
- Race pace target
- Race time prediction
- Long-run heart-rate drift
- Workout completion adherence
- Missed workout impact

### 3.7 AI Coach

- Daily workout recommendation
- Explain recommendation with evidence
- Analyze recent workout
- Explain fatigue/recovery signals
- Suggest workout adjustment
- Answer training questions
- Update plan after user approval
- Generate weekly summary
- Identify training risks
- Preserve recommendation history
- Ask for subjective feedback when data is incomplete
- Avoid medical diagnosis

### 3.8 Human-in-the-Loop Adjustment

- Suggest adjustment
- Explain evidence
- User accepts
- User edits
- User rejects
- User discusses
- System applies accepted change
- System records decision and reason
- System learns preference/response over time

### 3.9 Agent Inbox and Notifications

- Recommendation inbox
- Recommendation priority
- Recommendation status: pending, accepted, rejected, edited, expired
- LINE notification
- Email notification
- Push notification in future mobile app
- Notification preferences
- Quiet hours
- Notification delivery log

### 3.10 Memory

- Conversation memory
- Athlete profile memory
- Athlete preference memory
- Agent-derived memory
- Confidence threshold for derived memory
- Memory audit/review UI
- Memory source and creation date
- Memory revocation/editing

### 3.11 Event-Driven and Scheduled Work

- Activity ingested event
- Health data updated event
- Sleep data updated event
- Recovery calculated event
- Training plan created event
- Workout completed event
- Workout skipped event
- Training load changed event
- Race created event
- Training recommendation created event
- Training plan adjusted event
- Daily briefing job
- Recovery analysis job
- Weekly training review job
- Monthly progress report job

### 3.12 Agent Observability

- Agent run records
- Trigger type
- Model
- Prompt version
- Tool calls
- Tool results
- Context snapshot
- Result
- Latency
- Token usage
- Cost
- User feedback
- Recommendation outcome
- Evaluation dataset for regression testing

### 3.13 Safety and Reliability

- No disease diagnosis
- No definitive injury diagnosis
- Pain/injury escalation language
- Human confirmation for significant plan changes
- Explainable recommendation evidence
- Conservative defaults under uncertainty
- Recommendation history
- Audit trail for agent actions
- Data quality warnings
- Fallback behavior when wearable data is missing

### 3.14 Future Content and Discovery

These are valuable but not MVP:

- Running news feed
- Training discussion summaries
- Race discovery
- Equipment discussion
- Research paper summaries
- YouTube/RSS/blog ingestion
- Deduplication and classification
- Personalized content feed
- Multi-agent research/race/coach split

---

## 4. Recommended MVP

The strongest MVP is the smallest version that proves the core Johnny loop:

```text
Training data -> Analytics -> AI recommendation -> User approval -> Training adjustment -> Notification
```

### MVP Scope

1. User profile
2. Race goal
3. Training calendar
4. Manual activity entry plus one primary integration, preferably Strava first or Garmin if API access is ready
5. Health/recovery data model with manual MVP fallback
6. Deterministic analytics engine
7. Daily recommendation on Today page
8. AI coach conversation
9. Training adjustment workflow
10. Agent Inbox
11. LINE notification
12. Agent run and recommendation history

### Suggested Deferrals

- Apple Health until an iOS companion app exists
- Multi-agent architecture
- Full content/news system
- Race discovery
- Travel planning
- Nutrition
- Advanced equipment advice
- Broad social media ingestion

Reasoning:

The MVP should prove whether Johnny can produce trustworthy, personalized, explainable daily training recommendations. Everything else depends on that trust.

---

## 5. Proposed System Architecture

### 5.1 High-Level Shape

```text
Clients
  Web
  LINE
  Future iOS

API / BFF

Application Layer
  User
  Athlete
  Race
  Training
  Activity
  Health
  Recovery
  Recommendation
  Notification
  Agent

Domain Services
  TrainingPlanService
  TrainingAnalyticsService
  RecoveryService
  RaceStrategyService
  RecommendationService
  AthleteContextService
  NotificationService

Infrastructure
  PostgreSQL
  Redis
  Queue / Event Bus
  External Integrations
  LLM Provider
  Notification Channels
```

### 5.2 Agent Runtime

Start with one orchestrator:

```text
Running Companion Agent
  Training Tools
  Health Tools
  Race Tools
  User Tools
  Notification Tools
```

Do not start with multi-agent. It adds coordination complexity before the product has enough proven agent workloads.

The agent should:

- Receive a narrow task and structured context.
- Call domain tools when it needs more context.
- Produce a recommendation, explanation, and proposed action.
- Never directly query the database.
- Never silently apply significant training plan changes.

### 5.3 Data Flow: Daily Recommendation

```text
Scheduled daily job
  -> Load athlete context
  -> Load today's planned workout
  -> Load recent activities
  -> Load recovery metrics
  -> Run deterministic analytics
  -> Call Running Companion Agent
  -> Create recommendation
  -> Show on Today page
  -> Optionally send LINE notification
  -> User accepts, edits, rejects, or discusses
  -> Apply approved plan adjustment
  -> Store decision and feedback
```

### 5.4 Data Flow: Completed Workout

```text
External activity webhook or manual entry
  -> Normalize activity
  -> Store activity
  -> Emit ActivityIngested
  -> Recalculate analytics
  -> Compare against planned workout
  -> Generate insight or recommendation if needed
  -> Add item to Agent Inbox
```

### 5.5 Data Flow: Conversation

```text
User message
  -> Conversation API
  -> Agent run created
  -> Agent calls domain tools
  -> Tools return structured context
  -> Agent responds with answer, evidence, and suggested action
  -> If action is proposed, create approval item
  -> User decision applies or rejects action
```

---

## 6. Proposed Domain Model

### 6.1 Core Entities

#### User

Represents the account.

Key fields:

- `id`
- `email`
- `display_name`
- `timezone`
- `unit_preference`
- `created_at`

#### AthleteProfile

Represents long-term running identity and constraints.

Key fields:

- `user_id`
- `experience_level` (nullable)
- `current_weekly_mileage_km`
- `preferred_training_days`
- `preferred_long_run_day`
- `max_runs_per_week`
- `injury_status`
- `injury_areas`
- `injury_notes`
- `training_preferences`

#### Race

Represents a target race.

Key fields:

- `id`
- `user_id`
- `name`
- `date`
- `distance`
- `target_time`
- `priority`
- `course_profile`
- `status`

#### TrainingPlan

Represents a plan for a race or training block.

Key fields:

- `id`
- `user_id`
- `race_id`
- `start_date`
- `end_date`
- `status`
- `version`

#### Workout

Represents one planned training session.

Key fields:

- `id`
- `training_plan_id`
- `scheduled_date`
- `type`
- `planned_distance`
- `planned_duration`
- `pace_range`
- `heart_rate_zone`
- `purpose`
- `status`
- `source`

#### Activity

Represents an actual completed activity.

Key fields:

- `id`
- `user_id`
- `source`
- `source_activity_id`
- `started_at`
- `sport_type`
- `distance`
- `duration`
- `average_pace`
- `average_heart_rate`
- `elevation_gain`
- `raw_payload_ref`

#### HealthMetric

Represents daily health/recovery data.

Key fields:

- `id`
- `user_id`
- `date`
- `sleep_duration`
- `sleep_quality`
- `hrv`
- `hrv_baseline`
- `resting_heart_rate`
- `stress_score`
- `source`

#### TrainingMetricSnapshot

Stores deterministic analytics for a date.

Key fields:

- `id`
- `user_id`
- `date`
- `weekly_distance`
- `previous_weekly_distance`
- `acute_load`
- `chronic_load`
- `load_ratio`
- `sleep_debt`
- `recovery_score`
- `readiness_label`

#### Recommendation

Represents an AI or system-generated suggestion.

Key fields:

- `id`
- `user_id`
- `type`
- `priority`
- `status`
- `title`
- `summary`
- `evidence`
- `proposed_action`
- `agent_run_id`
- `created_at`
- `expires_at`
- `user_decision`

#### PlanAdjustment

Represents an accepted or proposed change to the training plan.

Key fields:

- `id`
- `recommendation_id`
- `training_plan_id`
- `workout_id`
- `before`
- `after`
- `reason`
- `status`
- `approved_by_user_at`

#### Conversation

Represents a chat thread.

Key fields:

- `id`
- `user_id`
- `title`
- `created_at`
- `updated_at`

#### AgentRun

Represents one agent execution.

Key fields:

- `id`
- `user_id`
- `trigger`
- `model`
- `prompt_version`
- `context_summary`
- `tool_calls`
- `tool_results_ref`
- `result`
- `latency_ms`
- `token_usage`
- `cost`
- `created_at`

#### MemoryItem

Represents long-term profile, preference, or derived memory.

Key fields:

- `id`
- `user_id`
- `type`
- `content`
- `source`
- `confidence`
- `created_at`
- `last_confirmed_at`
- `status`

#### NotificationIntent

Represents what should be sent, independent of channel.

Key fields:

- `id`
- `user_id`
- `type`
- `priority`
- `payload`
- `channel_policy`
- `status`
- `created_at`

### 6.2 Important Relationships

- A `User` has one `AthleteProfile`.
- A `User` has many `Race` records.
- A `Race` may have one active `TrainingPlan`.
- A `TrainingPlan` has many `Workout` records.
- An `Activity` may be matched to a planned `Workout`.
- `HealthMetric` and `Activity` records feed `TrainingMetricSnapshot`.
- A `Recommendation` can propose one `PlanAdjustment`.
- A `PlanAdjustment` is applied only after approval.
- An `AgentRun` can create recommendations, memory candidates, or conversation responses.
- `NotificationIntent` is created by application services, then delivered by channel adapters.

---

## 7. Proposed Code Structure

The current repository already has a useful scaffold:

- `backend/src/` for backend code
- `backend/src/api/` for routes
- `backend/src/application/` for use cases and interfaces
- `backend/src/infrastructure/` for database, queue, integrations, logging
- `backend/src/worker/` and `backend/src/dispatcher/` for async/scheduled work
- `frontend/src/` for the Vue app
- `infra/terraform/` for AWS infrastructure

I would keep that structure and expand it by domain responsibility.

### 7.1 Backend

Proposed backend structure:

```text
backend/src/
  api/
    routes/
      auth.py
      athletes.py
      races.py
      training_plans.py
      workouts.py
      activities.py
      health.py
      recommendations.py
      conversations.py
      integrations.py
      notifications.py

  application/
    user/
    athlete/
    race/
    training/
    activity/
    health/
    recovery/
    recommendation/
    conversation/
    agent/
    notification/
    memory/
    interfaces/

  domain/
    user/
    athlete/
    race/
    training/
    activity/
    health/
    analytics/
    recommendation/
    memory/
    events/

  infrastructure/
    database/
      models/
      repositories/
      migrations/
    integrations/
      garmin/
      strava/
      line/
    llm/
    queue/
    cache/
    logging/
    observability/

  dispatcher/
    schedules/
      daily_briefing.py
      recovery_analysis.py
      weekly_review.py

  worker/
    handlers/
      activity_ingested.py
      health_data_updated.py
      recommendation_created.py
      notification_requested.py
```

### 7.2 Frontend

Proposed frontend structure:

```text
frontend/src/
  app/
    routes/
    layout/
    providers/

  features/
    today/
    conversation/
    agent-inbox/
    training-calendar/
    race-goals/
    profile/
    integrations/

  components/
    ui/
    charts/
    evidence/

  api/
    client.ts
    types.ts

  state/

  styles/
```

Frontend principles:

- Build the actual product UI first, not a marketing landing page.
- Make Today the first screen.
- Keep Conversation and Agent Inbox as separate workflows.
- Use evidence components consistently for recommendation explanations.
- Keep action states explicit: pending, accepted, rejected, edited, applied.

---

## 8. Agent Tool Design

Agent tools should expose domain-level operations, not raw persistence.

### Read Tools

- `getAthleteContext(user_id)`
- `getTrainingPlan(user_id, date_range)`
- `getTodayWorkout(user_id, date)`
- `getRecentActivities(user_id, days)`
- `getRecoveryState(user_id, date)`
- `getTrainingMetrics(user_id, date_range)`
- `getRaceContext(user_id, race_id)`
- `getRecommendationHistory(user_id, days)`
- `getAthleteMemories(user_id, memory_types)`

### Analysis Tools

These should call deterministic services:

- `calculateTrainingLoad(user_id, date_range)`
- `calculateRecoveryScore(user_id, date)`
- `calculatePaceZones(user_id)`
- `calculateRacePacing(race_id, target_time)`
- `analyzeWorkoutCompletion(workout_id, activity_id)`
- `detectTrainingRisk(user_id, date)`

### Write/Action Tools

These should usually create proposals, not directly mutate important state:

- `createRecommendation(user_id, recommendation_payload)`
- `proposeWorkoutAdjustment(workout_id, adjustment_payload)`
- `createPlanAdjustmentProposal(training_plan_id, payload)`
- `applyApprovedPlanAdjustment(adjustment_id)`
- `createNotificationIntent(user_id, payload)`
- `storeMemoryCandidate(user_id, payload)`

Important rule:

The agent can propose significant changes. Application services apply them only after user approval.

---

## 9. API Design Direction

Initial API groups:

- `GET /health`
- `GET /me`
- `GET /athlete/profile`
- `PATCH /athlete/profile`
- `POST /races`
- `GET /races`
- `GET /races/{race_id}`
- `POST /training-plans`
- `GET /training-plans/current`
- `GET /workouts/today`
- `PATCH /workouts/{workout_id}`
- `POST /activities/manual`
- `GET /activities`
- `POST /integrations/strava/connect`
- `POST /integrations/garmin/connect`
- `POST /integrations/webhooks/strava`
- `POST /integrations/webhooks/garmin`
- `GET /recommendations`
- `POST /recommendations/{recommendation_id}/accept`
- `POST /recommendations/{recommendation_id}/reject`
- `POST /recommendations/{recommendation_id}/discuss`
- `POST /conversations`
- `GET /conversations/{conversation_id}`
- `POST /conversations/{conversation_id}/messages`
- `GET /agent-runs/{agent_run_id}`

---

## 10. Event Model

Initial events:

- `RaceCreated`
- `TrainingPlanCreated`
- `WorkoutCompleted`
- `WorkoutSkipped`
- `ActivityIngested`
- `HealthDataUpdated`
- `SleepDataUpdated`
- `RecoveryCalculated`
- `TrainingMetricsCalculated`
- `TrainingRecommendationCreated`
- `TrainingAdjustmentProposed`
- `TrainingPlanAdjusted`
- `NotificationRequested`
- `NotificationDelivered`
- `AgentRunCompleted`
- `MemoryCandidateCreated`

Event use:

- Decouple ingestion, analytics, recommendations, and notifications.
- Keep user-facing API calls fast.
- Allow scheduled and event-driven agent runs.
- Preserve auditability.

---

## 11. Technology Direction

Given the updated product preference, I would use:

- Frontend: Vue + Vite + TypeScript
- Backend: Python + FastAPI
- Database: PostgreSQL
- Cache/queue support: Redis if needed
- Background jobs: current worker/dispatcher scaffold first, SQS later if deploying on AWS
- Infrastructure: existing Terraform/AWS ECS direction
- Agent runtime: custom application-level orchestration first, optionally OpenAI Agents SDK once tool contracts stabilize
- LLM provider: keep behind an infrastructure adapter

Why not switch the backend immediately to NestJS/.NET:

- The current repo already has a Python backend that fits analytics, integrations, and AI orchestration well.
- The frontend should move from the current scaffold to Vue/Vite during the foundation feature before product UI work starts.
- Python is a practical fit for analytics, integrations, and AI orchestration.
- The product risk is not framework choice; it is the quality of the domain model, data normalization, analytics, and agent tool boundaries.

Potential future switch:

- If server-rendered web becomes important, Nuxt can be reconsidered within the Vue ecosystem.
- If mobile API consolidation or a larger TypeScript backend team becomes the priority, NestJS can be reconsidered.
- If enterprise-grade typed backend workflows become the priority, .NET can be reconsidered.

---

## 12. MVP Build Sequence

This is a proposed order, not a coding plan.

### Phase 1: Product Foundation

- User profile
- Athlete profile
- Race goal
- Training calendar
- Manual workout/activity input

Goal:

Johnny can represent the athlete, race target, and plan even before integrations are ready.

### Phase 2: Analytics Foundation

- Activity model
- Health metric model
- Deterministic training analytics
- Recovery scoring
- Today context aggregation

Goal:

Johnny has reliable structured context for recommendations.

### Phase 3: Recommendation Loop

- Daily recommendation service
- Evidence model
- Recommendation history
- Accept/reject/edit workflow
- Plan adjustment application

Goal:

Johnny can recommend and adjust training with user approval.

### Phase 4: Agent Conversation

- Conversation API
- Running Companion Agent
- Domain tools
- Agent run tracing
- Action proposal flow from chat

Goal:

Users can ask contextual training questions and receive evidence-backed responses.

### Phase 5: Integration and Proactivity

- Strava or Garmin integration
- Activity ingestion events
- Scheduled daily briefing
- Agent Inbox
- LINE notification

Goal:

Johnny becomes proactive and data-connected.

---

## 13. Key Product Decisions to Discuss

1. Should the MVP start with manual data input plus Strava, or require Garmin from day one?
2. Should Johnny generate full training plans in V1, or start by adapting a user-created/imported plan?
3. How conservative should automatic recommendations be when recovery data is missing?
4. Should the first user experience be race-goal onboarding or Today dashboard?
5. Should Conversation be available immediately, or only after profile/race/plan setup?
6. What level of training science should the deterministic analytics use in V1?
7. Should LINE notification be mandatory for MVP, or can Agent Inbox prove the loop first?
8. How should Johnny handle pain reports and injury-related questions?
9. Should derived memory be invisible, user-reviewable, or user-editable from the beginning?
10. What is the first target user: beginner, intermediate marathon runner, or performance-focused runner?

---

## 14. My Recommended Direction

Start with a conservative, evidence-first MVP:

- Today is the primary UI.
- Race goal and training calendar are required foundation.
- Manual activity/health input exists as fallback.
- Add one real activity integration as soon as possible.
- Build deterministic analytics before relying on agent recommendations.
- Use a single Running Companion Agent.
- Keep all important data access behind domain tools.
- Treat agent outputs as recommendations and proposals.
- Require user approval before meaningful plan changes.
- Store every recommendation, decision, and agent run for observability.

The first product milestone should be:

> A runner with a race goal can open Johnny each morning, see today's workout, see recovery/training evidence, get a useful recommendation, approve an adjustment, and receive a notification.

If that loop feels trustworthy, the product has a strong base for race strategy, content, richer integrations, and future multi-agent work.
