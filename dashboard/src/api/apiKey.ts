// API key for an agent running with AUTH_ENABLED=1. Kept in this browser only.
const STORAGE_KEY = 'flowkit.apiKey'

/** Fired when the agent answers 401, so the key form can open. */
export const AUTH_REQUIRED_EVENT = 'flowkit:auth-required'

export function getApiKey(): string | null {
  try {
    return localStorage.getItem(STORAGE_KEY)
  } catch {
    return null
  }
}

export function setApiKey(key: string | null) {
  try {
    if (key) localStorage.setItem(STORAGE_KEY, key)
    else localStorage.removeItem(STORAGE_KEY)
  } catch {
    // storage blocked — the key lasts until reload
  }
}

export function authHeaders(): Record<string, string> {
  const key = getApiKey()
  return key ? { 'X-API-Key': key } : {}
}
