export type ViewKey = 'today' | 'plan' | 'johnny' | 'athlete' | 'data' | 'conversation'

export interface CurrentUser {
  id: string
  email?: string | null
  display_name?: string | null
  capabilities: string[]
}

export interface AthleteProfileResponse {
  timezone?: string | null
  experience_level?: 'beginner' | 'intermediate' | 'advanced' | null
  current_weekly_mileage_km?: number | null
  preferred_training_days?: string[] | null
  preferred_long_run_day?: string | null
  max_runs_per_week?: number | null
  max_hard_sessions_per_week?: number | null
  unit_preference?: 'metric' | 'imperial' | null
  threshold_pace_seconds_per_km?: number | null
  resting_heart_rate_bpm?: number | null
  max_heart_rate_bpm?: number | null
  training_preferences?: Record<string, unknown>
  injury_status?: 'none' | 'current' | 'recent' | 'recurring' | null
  injury_areas?: string[] | null
  injury_notes?: string | null
}

export interface AthleteProfileSavePayload {
  timezone: string
  experience_level: 'beginner' | 'intermediate' | 'advanced' | null
  current_weekly_mileage_km: number
  preferred_training_days: string[]
  preferred_long_run_day: string
  max_runs_per_week: number
  max_hard_sessions_per_week: number
  unit_preference: 'metric' | 'imperial'
  threshold_pace_seconds_per_km: number | null
  resting_heart_rate_bpm: number | null
  max_heart_rate_bpm: number | null
  injury_status: 'none' | 'current' | 'recent' | 'recurring'
  injury_areas: string[]
  injury_notes: string | null
}

export interface AuthResponse {
  data: {
    user: CurrentUser
  }
}

export interface EmailPasswordSignupPayload {
  display_name: string
  email: string
  password: string
}

export interface EmailPasswordLoginPayload {
  email: string
  password: string
}

export interface RaceSummary {
  id: string
  name: string
  date: string
  raceDate: string
  distance: string
  goal: string
  daysRemaining: number
  ascentMeters?: number | null
  descentMeters?: number | null
  terrainDifficulty?: 'runnable' | 'mixed' | 'technical' | null
  cutoffSeconds?: number | null
  goalIntent?: 'complete' | 'perform' | null
}

export interface WeeklyActivityPoint {
  dayLabel: string
  distanceKm: number
  loadLabel: string
}

export interface PlanPhase {
  id: string
  label: string
  status: 'done' | 'current' | 'next'
  summary: string
}

export interface RaceGoalCreatePayload {
  name: string
  race_date: string
  distance_meters: number
  target_finish_seconds?: number
  priority: string
  ascent_meters?: number
  descent_meters?: number
  terrain_difficulty?: 'runnable' | 'mixed' | 'technical'
  cutoff_seconds?: number
  goal_intent?: 'complete' | 'perform'
}

export interface RaceGoalUpdatePayload extends RaceGoalCreatePayload {
  status: string
}

export interface PreparationAssessment {
  status: 'gap' | 'unknown' | 'on_track'
  factors: string[]
  explanation_zh: string
  policy_version: string
}

export type TrainingPlanType = 'race' | 'maintenance'

export type TrainingPlanPhase = 'base' | 'build' | 'peak' | 'taper' | 'race' | 'maintenance'

export interface TrainingPlanPhaseSegment {
  phase: TrainingPlanPhase
  starts_on: string
  ends_on: string
  focus?: string
}

export interface TrainingPlanMetadata {
  phase_segments?: TrainingPlanPhaseSegment[]
  [key: string]: unknown
}

export interface TrainingPlanResponse {
  id: string | null
  user_id: string
  race_id: string | null
  name: string
  status: string
  starts_on: string
  ends_on: string
  metadata: TrainingPlanMetadata
  preparation_assessment?: PreparationAssessment | null
  workouts: unknown[]
}

export interface TrainingPlanRegenerationRequest {
  client_request_id: string
  race_id: string | null
  plan_type: TrainingPlanType
}

export interface TrainingPlanRegenerationQuota {
  quota_day: string
  limit: number
  used: number
  remaining: number
  available: boolean
  next_available_at: string | null
}

export interface TrainingPlanRegenerationStrategy {
  race_id: string | null
  plan_type: TrainingPlanType
  reason: string
  starts_on: string
  plan_horizon_weeks: number
}

export interface TrainingPlanRegenerationRun {
  run_id: string
  status: string
  workflow_name: string
  poll_url: string
}

export interface AgentRunResponse {
  id: string | null
  status: string
  workflow_name: string
  finished_at: string | null
  error_message: string | null
  daily_advice_id?: string | null
}

export interface DailyAdvice {
  id: string
  adviceDate: string
  state: 'pending' | 'ready' | 'sync_failed' | 'generation_failed' | 'no_plan'
  dataFreshness: 'fresh' | 'limited' | 'stale'
  generatedAt: string | null
  sourceSyncRunId: string | null
  sourceRunId: string | null
  planVersionId: string | null
  workoutId: string | null
  executionMode: 'follow_plan' | 'ease_off' | 'rest' | 'completed' | null
  planWeek: { startsOn: string; endsOn: string } | null
  facts: Record<string, unknown> | null
  weekSummary: string | null
  todayExecution: string | null
  workoutGuide: { purpose: string; expectedFeel: string; ifTooHard: string; ifTooEasy: string } | null
}

export interface QueuedDailyAdviceRun {
  run_id: string
  status: string
  workflow_name: string
  poll_url: string
}

export interface TrainingPlanRegenerationOptions {
  quota: TrainingPlanRegenerationQuota
  default_strategy: TrainingPlanRegenerationStrategy
  in_flight_run: TrainingPlanRegenerationRun | null
  run: TrainingPlanRegenerationRun | null
}

export type TrainingPlanRegenerationStartResponse = TrainingPlanRegenerationOptions

export interface EvidenceItem {
  source: string
  metric: string
  value: string
  summary: string
  tone?: 'info' | 'warning' | 'danger' | 'success'
}

export interface AthleteBaselineSnapshot {
  weeklyMileage: string
  experience: string
  injuryStatus: string
  rhythm: string
  recentMetrics: string[]
}

export interface SignalCoverageItem {
  id: 'activity' | 'sleep' | 'hrv' | 'resting_hr' | 'training_load' | 'athlete_baseline'
  label: string
  covered: boolean
  source: string
}

export type WorkoutStepType = 'warmup' | 'work' | 'recovery' | 'cooldown' | 'repeat' | 'drill' | 'stride' | 'hill' | 'free_run'
export type WorkoutTargetKind = 'pace' | 'heart_rate' | 'rpe'
export type WorkoutTargetConfidence = 'high' | 'medium' | 'low'

export interface WorkoutTarget {
  kind: WorkoutTargetKind
  zone?: string | null
  heartRateZone?: string | null
  rpe?: number | null
  paceRangeSecondsPerKm?: number[] | null
  heartRateRangeBpm?: number[] | null
  confidence?: WorkoutTargetConfidence | null
  paceSource?: 'threshold_pace' | 'completed_race' | 'paired_easy_activities' | 'goal_time' | null
}

export interface WorkoutStep {
  type: WorkoutStepType
  durationSeconds?: number | null
  distanceMeters?: number | null
  target?: WorkoutTarget | null
  repeatCount?: number | null
  steps?: WorkoutStep[]
  notes?: string | null
  gradeNotes?: string | null
}

export interface WorkoutSummary {
  id: string
  weekday: string
  dateLabel: string
  scheduledFor?: string
  type: string
  workoutType?: string
  raceName?: string
  raceGoalId?: string
  racePriority?: 'primary' | 'secondary' | 'tune_up'
  purpose: string
  distance?: string
  duration?: string
  pace?: string
  heartRateZone?: string
  phase?: string
  coachNote?: string
  stepSummary?: string
  steps?: WorkoutStep[]
  status: string
}

export interface RecommendationSummary {
  id: string
  priority: 'info' | 'warning' | 'danger'
  title: string
  rationale: string
  proposedAction: string
  status: string
}

export type TodayDecisionState = 'run' | 'adjust' | 'rest'

export interface TodayDecision {
  state: TodayDecisionState
  label: '我可以' | '不太對勁' | '先收一下' | '今天已完成' | '建議更新中'
  actionLabel: '開始跑步' | '接受調整' | '記錄休息' | '查看 Johnny 建議'
  tone: 'run' | 'adjust' | 'rest'
  voice: string
  memoryInsight?: string
}

export type RecommendationPriority = 'low' | 'medium' | 'high'

export type RecommendationStatus = 'pending' | 'accepted' | 'rejected' | 'edited' | 'expired' | 'applied'

export interface LinkedRecommendationContext {
  id: string
  title: string
  status: RecommendationStatus
  statusLabel: string
  evidenceSummary: string
  evidence: EvidenceItem[]
}

export interface ProposedActionCard {
  id: string
  title: string
  summary: string
  proposedAction: string
  rationale: string
  evidence: EvidenceItem[]
}

export interface ConversationMessage {
  id: string
  role: 'user' | 'johnny'
  authorLabel: string
  content: string
  timestampLabel: string
  evidence?: EvidenceItem[]
  proposedAction?: ProposedActionCard
  runRef?: string
}

export interface ConversationThread {
  id: string
  title: string
  summary: string
  updatedLabel: string
  linkedRecommendation?: LinkedRecommendationContext
  messages: ConversationMessage[]
}

export interface InboxRecommendation {
  id: string
  title: string
  summary: string
  proposedAction: string
  rationale: string
  priority: RecommendationPriority
  priorityLabel: string
  status: RecommendationStatus
  statusLabel: string
  expiresAtLabel?: string
  evidence: EvidenceItem[]
}

export interface ProviderOption {
  id: string
  name: string
  status: 'connected' | 'available' | 'future'
  statusLabel: string
  coverage: string[]
  description: string
}

export interface IntegrationConnectionPayload {
  provider: string
  provider_account_id: string
  credential_secret_ref?: string
}

export interface GarminConnectPayload {
  email: string
  password: string
  region: 'global' | 'china'
}

export interface SyncResourceSummary {
  fetched?: number
  stored?: number
  duplicates?: number
  failed?: number
  errors?: string[]
}

export interface IntegrationConnectionResponse {
  id: string
  provider: string
  provider_account_id?: string
  provider_display_name?: string | null
  status: 'active' | 'replaced' | 'disconnected' | string
  credential_status: 'active' | 'requires_reauth' | 'deleted' | string
  sync_status: 'idle' | 'running' | 'failed' | string
  last_sync_started_at?: string | null
  last_sync_completed_at?: string | null
  last_sync_error?: string | null
  sync_warning?: string | null
  has_partial_failures?: boolean
  sync_summary?: {
    resources: Record<string, SyncResourceSummary>
  } | null
  daily_advice_run?: QueuedDailyAdviceRun | null
}

export interface IntegrationConnectionEnvelope {
  data: IntegrationConnectionResponse
}

export interface ConversationMessageResponse {
  data: {
    message: {
      content: string
      recommendation_id?: string | null
      agent_status?: string
      agent_output?: string
    }
    run_ref: string
  }
}
