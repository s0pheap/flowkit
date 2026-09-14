import { AUTH_REQUIRED_EVENT, authHeaders } from './apiKey'

const BASE = ''  // same origin, proxied by Vite in dev

export async function fetchAPI<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...options,
    headers: { 'Content-Type': 'application/json', ...authHeaders(), ...options?.headers },
  })
  if (res.status === 401) window.dispatchEvent(new Event(AUTH_REQUIRED_EVENT))
  if (!res.ok) {
    const err = await res.text().catch(() => res.statusText)
    throw new Error(`API ${res.status}: ${err}`)
  }
  return res.json()
}

export async function patchAPI<T>(path: string, body: Record<string, unknown>): Promise<T> {
  return fetchAPI<T>(path, { method: 'PATCH', body: JSON.stringify(body) })
}
