import { useCallback, useEffect, useState, type FormEvent, type ReactNode } from 'react'
import { AUTH_REQUIRED_EVENT, authHeaders, getApiKey, setApiKey } from '../api/apiKey'
import { useTranslation } from '../i18n/useTranslation'

type Me = { auth_enabled: boolean; name: string; is_admin: boolean; project_ids: string[] | null }
type State = { kind: 'checking' } | { kind: 'ok'; me: Me } | { kind: 'needKey'; rejected: boolean } | { kind: 'unreachable' }

/** Asks for an API key when the agent runs with AUTH_ENABLED=1; renders the app untouched otherwise. */
export function ApiKeyGate({ children }: { children: ReactNode }) {
  const { t } = useTranslation()
  const [state, setState] = useState<State>({ kind: 'checking' })
  const [draft, setDraft] = useState('')

  const check = useCallback(async () => {
    try {
      const res = await fetch('/api/auth/me', { headers: authHeaders() })
      if (res.status === 401) {
        setState({ kind: 'needKey', rejected: getApiKey() !== null })
        return false
      }
      if (!res.ok) throw new Error(String(res.status))
      setState({ kind: 'ok', me: await res.json() })
      return true
    } catch {
      setState({ kind: 'unreachable' })
      return false
    }
  }, [])

  useEffect(() => {
    void check()
    const onAuthRequired = () => { void check() }
    window.addEventListener(AUTH_REQUIRED_EVENT, onAuthRequired)
    return () => window.removeEventListener(AUTH_REQUIRED_EVENT, onAuthRequired)
  }, [check])

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    const key = draft.trim()
    if (!key) return
    setApiKey(key)
    // Reload so every page and the live socket start over with the key.
    if (await check()) window.location.reload()
    else setApiKey(null)
  }

  if (state.kind === 'checking') return null
  if (state.kind === 'ok' || state.kind === 'unreachable') {
    // Unreachable: let the app render and show its own "agent offline" states.
    return <>{children}</>
  }

  return (
    <div className="flex h-screen items-center justify-center p-4" style={{ background: 'var(--bg)', color: 'var(--text)' }}>
      <form
        onSubmit={submit}
        className="w-full max-w-sm flex flex-col gap-3 p-5 rounded border"
        style={{ background: 'var(--surface)', borderColor: 'var(--border)' }}
      >
        <div className="flex items-center gap-2.5">
          <span className="w-[22px] h-[22px] rounded flex items-center justify-center text-xs font-bold" style={{ background: 'var(--accent)', color: 'var(--bg)' }}>F</span>
          <span className="text-xs font-bold tracking-widest">{t('app.brandName')}</span>
        </div>
        <label htmlFor="fk-api-key" className="text-xs" style={{ color: 'var(--muted)' }}>{t('auth.prompt')}</label>
        <input
          id="fk-api-key"
          type="password"
          autoComplete="off"
          autoFocus
          value={draft}
          onChange={e => setDraft(e.target.value)}
          placeholder="fk_…"
          className="text-xs px-2.5 py-2 rounded outline-none"
          style={{ background: 'var(--card)', color: 'var(--text)', border: '1px solid var(--border)' }}
        />
        {state.rejected && <span className="text-[11px]" style={{ color: 'var(--red)' }}>{t('auth.rejected')}</span>}
        <button
          type="submit"
          className="text-xs px-2.5 py-2 rounded font-bold tracking-wide"
          style={{ background: 'var(--accent)', color: 'var(--bg)' }}
        >
          {t('auth.submit')}
        </button>
      </form>
    </div>
  )
}

/** Signed-in name plus a sign-out link, for the sidebar. Renders nothing when no key is stored. */
export function ApiKeyStatus() {
  const { t } = useTranslation()
  const [name, setName] = useState<string | null>(null)
  const hasKey = getApiKey() !== null

  useEffect(() => {
    if (!hasKey) return
    fetch('/api/auth/me', { headers: authHeaders() })
      .then(r => (r.ok ? r.json() : null))
      .then((me: Me | null) => setName(me?.name ?? null))
      .catch(() => setName(null))
  }, [hasKey])

  if (!hasKey) return null
  return (
    <div className="flex items-center justify-between text-[10px] tracking-wide" style={{ color: 'var(--muted)' }}>
      <span className="truncate" style={{ color: 'var(--text)' }}>{name ?? '…'}</span>
      <button
        type="button"
        className="hover:opacity-80"
        onClick={() => { setApiKey(null); window.location.reload() }}
      >
        {t('auth.signOut')}
      </button>
    </div>
  )
}
