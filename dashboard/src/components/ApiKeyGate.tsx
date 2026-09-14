import { useCallback, useEffect, useState, type FormEvent, type ReactNode } from 'react'
import { KeyRound, LogOut } from 'lucide-react'
import { AUTH_REQUIRED_EVENT, authHeaders, getApiKey, setApiKey } from '../api/apiKey'
import { useTranslation } from '../i18n/useTranslation'
import { BrandMark } from './BrandMark'

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
    <div
      className="flex min-h-screen items-center justify-center p-4"
      style={{ background: 'radial-gradient(900px 500px at 50% -10%, rgb(111 120 247 / 0.18), transparent 70%), var(--bg)' }}
    >
      <form onSubmit={submit} className="w-full max-w-[400px] flex flex-col gap-6 p-8 rounded-2xl border border-border bg-card" style={{ boxShadow: 'var(--shadow-pop)' }}>
        <div className="flex flex-col items-center gap-4 text-center">
          <BrandMark size={44} />
          <div className="flex flex-col gap-1.5">
            <h1 className="m-0 text-xl font-semibold tracking-[-0.02em]">{t('auth.title')}</h1>
            <p className="m-0 text-[14px] leading-relaxed text-muted-foreground">{t('auth.prompt')}</p>
          </div>
        </div>
        <div className="flex flex-col gap-2">
          <label htmlFor="fk-api-key" className="text-[13px] font-medium text-muted-foreground">{t('auth.keyLabel')}</label>
          <div className="flex items-center gap-2 h-11 rounded-lg border border-border bg-surface px-3 focus-within:border-primary transition-colors">
            <KeyRound size={16} className="text-faint shrink-0" />
            <input
              id="fk-api-key"
              type="password"
              autoComplete="off"
              autoFocus
              value={draft}
              onChange={e => setDraft(e.target.value)}
              placeholder="fk_…"
              className="flex-1 min-w-0 bg-transparent outline-none text-[14px] font-mono placeholder:text-faint"
            />
          </div>
          {state.rejected && <span className="text-[13px]" style={{ color: 'var(--red)' }}>{t('auth.rejected')}</span>}
        </div>
        <button
          type="submit"
          disabled={!draft.trim()}
          className="h-11 rounded-lg text-[14px] font-semibold bg-primary text-primary-foreground hover:brightness-110 transition disabled:opacity-50"
        >
          {t('auth.submit')}
        </button>
      </form>
    </div>
  )
}

/** Signed-in account row with sign out, for the sidebar. Renders nothing when no key is stored. */
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
    <div className="flex items-center gap-2.5 rounded-lg px-2 py-1.5">
      <span className="w-8 h-8 rounded-full flex items-center justify-center text-[13px] font-semibold uppercase bg-accent-soft text-brand shrink-0">
        {(name ?? '?').slice(0, 1)}
      </span>
      <span className="flex-1 min-w-0 truncate text-[14px] font-medium">{name ?? '…'}</span>
      <button
        type="button"
        title={t('auth.signOut')}
        aria-label={t('auth.signOut')}
        className="w-8 h-8 rounded-lg flex items-center justify-center text-faint hover:text-foreground hover:bg-card-hover transition-colors"
        onClick={() => { setApiKey(null); window.location.reload() }}
      >
        <LogOut size={16} />
      </button>
    </div>
  )
}
