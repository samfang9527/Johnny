export type ViewKey = 'today' | 'calendar' | 'inbox' | 'conversation' | 'athlete-settings' | 'sources'

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
  unit_preference?: 'metric' | 'imperial' | null
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
  unit_preference: 'metric' | 'imperial'
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
  name: string
  date: string
  distance: string
  goal: string
  daysRemaining: number
}

export interface RaceGoalCreatePayload {
  name: string
  race_date: string
  distance_meters: number
  target_finish_seconds?: number
  priority: string
}

export interface EvidenceItem {
  source: string
  metric: string
  value: string
  summary: string
  tone?: 'info' | 'warning' | 'danger' | 'success'
}

export interface WorkoutSummary {
  id: string
  weekday: string
  dateLabel: string
  type: string
  purpose: string
  distance?: string
  duration?: string
  pace?: string
  heartRateZone?: string
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
