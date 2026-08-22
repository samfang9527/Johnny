import type { ConversationMessageResponse, IntegrationConnectionPayload } from '../types'

export function getApiBaseUrl(): string {
  return import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'
}

async function requestJson<T>(path: string, init: RequestInit): Promise<T> {
  const response = await fetch(`${getApiBaseUrl()}/api/v1${path}`, {
    headers: {
      'Content-Type': 'application/json',
    },
    ...init,
  })
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`)
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

export function listRecommendations(): Promise<{ data: Array<Record<string, unknown>> }> {
  return getJson('/recommendations')
}

export function listTrainingPlans(): Promise<{ data: Array<Record<string, unknown>> }> {
  return getJson('/training-plans')
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
