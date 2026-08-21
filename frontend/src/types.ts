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
