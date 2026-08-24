import type {
  AuthResponse,
  ConversationMessageResponse,
  CurrentUser,
  EmailPasswordLoginPayload,
  EmailPasswordSignupPayload,
  IntegrationConnectionPayload,
  RaceGoalCreatePayload,
} from '../types'

export function getApiBaseUrl(): string {
  return import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000'
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

export function getTodayContext(anchorDate: string): Promise<{ data: Record<string, unknown> }> {
  return getJson(`/today?anchor_date=${encodeURIComponent(anchorDate)}`)
}

export function getCurrentUser(): Promise<{ data: CurrentUser }> {
  return getJson('/me')
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

export function listRecommendations(): Promise<{ data: Array<Record<string, unknown>> }> {
  return getJson('/recommendations')
}

export function listTrainingPlans(): Promise<{ data: Array<Record<string, unknown>> }> {
  return getJson('/training-plans')
}

export function listRaceGoals(raceDateFrom: string, raceDateTo: string): Promise<{ data: Array<Record<string, unknown>> }> {
  return getJson(`/races?race_date_from=${encodeURIComponent(raceDateFrom)}&race_date_to=${encodeURIComponent(raceDateTo)}&limit=100&offset=0`)
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

export function submitConversationMessage(content: string): Promise<ConversationMessageResponse> {
  return postJson('/conversations/messages', { content })
}
