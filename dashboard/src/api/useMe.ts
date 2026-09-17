import { useEffect, useState } from 'react'
import { authHeaders } from './apiKey'

export type Me = {
  auth_enabled: boolean
  name: string
  is_admin: boolean
  project_ids: string[] | null
}

// Who the stored key belongs to doesn't change while the page is open, and several
// places ask (the sidebar, the Guide, the admin gate), so the answer is fetched once.
let cached: Promise<Me | null> | null = null

export function fetchMe(): Promise<Me | null> {
  if (!cached) {
    cached = fetch('/api/auth/me', { headers: authHeaders() })
      .then(r => (r.ok ? (r.json() as Promise<Me>) : null))
      .catch(() => null)
  }
  return cached
}

export function useMe(): { me: Me | null; loading: boolean } {
  const [me, setMe] = useState<Me | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    void fetchMe().then(result => {
      if (cancelled) return
      setMe(result)
      setLoading(false)
    })
    return () => { cancelled = true }
  }, [])

  return { me, loading }
}
