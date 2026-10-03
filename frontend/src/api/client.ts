import type {
  AthleteProfileSavePayload,
  AthleteProfileResponse,
  AgentRunResponse,
  AuthResponse,
  ConversationMessageResponse,
  CurrentUser,
  EmailPasswordLoginPayload,
  EmailPasswordSignupPayload,
  GarminConnectPayload,
  IntegrationConnectionEnvelope,
  IntegrationConnectionPayload,
  IntegrationConnectionResponse,
  RaceGoalCreatePayload,
  TrainingPlanRegenerationOptions,
  TrainingPlanRegenerationRequest,
  TrainingPlanRegenerationStartResponse,
  TrainingPlanResponse,
} from '../types'

export function getApiBaseUrl(): string {
  return import.meta.env.VITE_API_BASE_URL || getLocalApiBaseUrl()
}

export function getLocalApiBaseUrl(frontendUrl?: string): string {
  if (frontendUrl) {
    return localApiBaseUrlFromLocation(new URL(frontendUrl))
  }
  if (typeof window !== 'undefined') {
    return localApiBaseUrlFromLocation(window.location)
  }
  return 'http://127.0.0.1:8000'
}

function localApiBaseUrlFromLocation(location: Pick<Location, 'hostname' | 'protocol'>): string {
  if (location.hostname === 'localhost' || location.hostname === '127.0.0.1') {
    return `${location.protocol}//${location.hostname}:8000`
  }
  return 'http://127.0.0.1:8000'
}

export class ApiRequestError extends Error {
  status: number

  constructor(status: number, message = `Request failed: ${status}`) {
    super(message)
    this.name = 'ApiRequestError'
    this.status = status
  }
}

async function requestJson<T>(path: string, init: RequestInit): Promise<T> {
  const response = await fetch(`${getApiBaseUrl()}/api/v1${path}`, {
    headers: {
      'Content-Type': 'application/json',
    },
    credentials: 'include',
    ...init,
  })
  if (!response.ok) {
    throw new ApiRequestError(response.status)
  }
  return response.json() as Promise<T>
}

async function getJson<T>(path: string): Promise<T> {
  return requestJson(path, { method: 'GET' })
}

async function postJson<T>(path: string, payload?: unknown): Promise<T> {
  return requestJson(path, {
    method: 'POST',
    body: payload === undefined ? undefined : JSON.stringify(payload),
  })
}

async function putJson<T>(path: string, payload?: unknown): Promise<T> {
  return requestJson(path, {
    method: 'PUT',
    body: payload === undefined ? undefined : JSON.stringify(payload),
  })
}

async function deleteJson<T>(path: string): Promise<T> {
  return requestJson(path, { method: 'DELETE' })
}

export function getTodayContext(anchorDate: string): Promise<{ data: Record<string, unknown> }> {
  return getJson(`/today?anchor_date=${encodeURIComponent(anchorDate)}`)
}

export function getCurrentUser(): Promise<{ data: CurrentUser }> {
  return getJson('/me')
}

export function getAthleteProfile(): Promise<{ data: AthleteProfileResponse }> {
  return getJson('/athlete/profile')
}

export function saveAthleteProfile(payload: AthleteProfileSavePayload): Promise<{ data: AthleteProfileResponse }> {
  return putJson('/athlete/profile', payload)
}

export function signUpWithEmail(payload: EmailPasswordSignupPayload): Promise<AuthResponse> {
  return postJson('/auth/signup', payload)
}

export function signInWithEmail(payload: EmailPasswordLoginPayload): Promise<AuthResponse> {
  return postJson('/auth/login', payload)
}

export function signOut(): Promise<unknown> {
  return postJson('/auth/logout')
}

export function startGoogleSignIn(callbackUrl: string, displayName?: string): Promise<{ data: { authorization_url: string } }> {
  const displayNameQuery = displayName ? `&display_name=${encodeURIComponent(displayName)}` : ''
  return getJson(`/auth/google/start?callback_url=${encodeURIComponent(callbackUrl)}${displayNameQuery}`)
}

export function getGoogleSignInRedirectUrl(callbackUrl: string, displayName?: string, frontendOrigin?: string, timezone?: string): string {
  const params = new URLSearchParams({
    callback_url: callbackUrl,
    redirect: 'true',
  })
  if (displayName) {
    params.set('display_name', displayName)
  }
  if (frontendOrigin) {
    params.set('frontend_origin', frontendOrigin)
  }
  if (timezone) {
    params.set('timezone', timezone)
  }
  return `${getApiBaseUrl()}/api/v1/auth/google/start?${params.toString()}`
}

export function listRecommendations(): Promise<{ data: Array<Record<string, unknown>> }> {
  return getJson('/recommendations')
}

export function listTrainingPlans(): Promise<{ data: TrainingPlanResponse[] }> {
  return getJson('/training-plans')
}

export function getAgentRun(runId: string): Promise<{ data: AgentRunResponse }> {
  return getJson(`/agent-runs/${encodeURIComponent(runId)}`)
}

export function getTrainingPlanRegenerationOptions(): Promise<{ data: TrainingPlanRegenerationOptions }> {
  return getJson('/training-plans/regeneration-options')
}

export function startTrainingPlanRegeneration(payload: TrainingPlanRegenerationRequest): Promise<{ data: TrainingPlanRegenerationStartResponse }> {
  return postJson('/training-plans/regenerations', payload)
}

export function listRaceGoals(raceDateFrom: string, raceDateTo?: string): Promise<{ data: Array<Record<string, unknown>> }> {
  const params = new URLSearchParams({
    race_date_from: raceDateFrom,
    limit: '100',
    offset: '0',
  })
  if (raceDateTo) {
    params.set('race_date_to', raceDateTo)
  }
  return getJson(`/races?${params.toString()}`)
}

export function createRaceGoal(payload: RaceGoalCreatePayload): Promise<{ data: Record<string, unknown> }> {
  return postJson('/races', payload)
}

export function acceptRecommendation(recommendationId: string): Promise<unknown> {
  return postJson(`/recommendations/${recommendationId}/accept`)
}

export function rejectRecommendation(recommendationId: string): Promise<unknown> {
  return postJson(`/recommendations/${recommendationId}/reject`)
}

export function discussRecommendation(recommendationId: string, content: string): Promise<unknown> {
  return postJson(`/recommendations/${recommendationId}/discuss`, { content })
}

export function connectIntegration(payload: IntegrationConnectionPayload): Promise<unknown> {
  return postJson('/integrations/connections', payload)
}

export function connectGarminIntegration(payload: GarminConnectPayload): Promise<IntegrationConnectionEnvelope> {
  return postJson('/integrations/garmin/connect', payload)
}

export function listIntegrationConnections(): Promise<{ data: IntegrationConnectionResponse[] }> {
  return getJson('/integrations/connections')
}

export function syncIntegrationConnection(connectionId: string): Promise<IntegrationConnectionEnvelope> {
  return postJson(`/integrations/connections/${encodeURIComponent(connectionId)}/sync`)
}

export function disconnectIntegrationConnection(connectionId: string): Promise<IntegrationConnectionEnvelope> {
  return deleteJson(`/integrations/connections/${encodeURIComponent(connectionId)}`)
}

export function submitConversationMessage(content: string): Promise<ConversationMessageResponse> {
  return postJson('/conversations/messages', { content })
}
