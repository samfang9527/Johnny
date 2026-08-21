export type ViewKey = 'today' | 'calendar' | 'inbox' | 'conversation' | 'sources'

export interface RaceSummary {
  name: string
  date: string
  distance: string
  goal: string
  daysRemaining: number
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

export interface ConversationMessageResponse {
  data: {
    message: {
      content: string
      recommendation_id?: string | null
    }
    run_ref: string
  }
}
