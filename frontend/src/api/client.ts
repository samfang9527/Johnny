import type { IntegrationConnectionPayload } from '../types'

export function getApiBaseUrl(): string {
  return import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'
}

async function postJson<T>(path: string, payload?: unknown): Promise<T> {
  const response = await fetch(`${getApiBaseUrl()}/api/v1${path}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: payload === undefined ? undefined : JSON.stringify(payload),
  })
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`)
  }
  return response.json() as Promise<T>
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
