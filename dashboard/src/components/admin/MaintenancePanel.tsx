import { useCallback, useEffect, useState } from 'react'
import { Link2, Loader2, RefreshCw } from 'lucide-react'

import { fetchAPI } from '../../api/client'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { useTranslation } from '../../i18n/useTranslation'

type ProjectRow = { id: string; name: string }
type RefreshResult = { refreshed: number; found: number; note?: string }

export function MaintenancePanel({ onError }: { onError: (e: string | null) => void }) {
  const { t } = useTranslation()
  const [projects, setProjects] = useState<ProjectRow[] | null>(null)
  const [selected, setSelected] = useState('')
  const [connected, setConnected] = useState<boolean | null>(null)
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState<RefreshResult | null>(null)

  const loadHealth = useCallback(async () => {
    try {
      const h = await fetchAPI<{ extension_connected: boolean }>('/health')
      setConnected(h.extension_connected)
    } catch {
      setConnected(false)
    }
  }, [])

  useEffect(() => {
    void (async () => {
      try {
        const rows = await fetchAPI<ProjectRow[]>('/api/projects')
        setProjects(rows)
        if (rows.length > 0) setSelected(rows[rows.length - 1].id)
      } catch (e) {
        onError(e instanceof Error ? e.message : String(e))
        setProjects([])
      }
    })()
    void loadHealth()
  }, [onError, loadHealth])

  const refresh = async () => {
    if (!selected) return
    setBusy(true)
    setResult(null)
    onError(null)
    // The signing call goes through the extension, so re-check before blaming the user.
    await loadHealth()
    try {
      setResult(await fetchAPI<RefreshResult>(`/api/flow/refresh-urls/${selected}`, { method: 'POST' }))
    } catch (e) {
      onError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flex flex-col gap-5">
      <section className="rounded-xl border border-border bg-card p-4 flex flex-col gap-3">
        <div className="flex items-center justify-between gap-3 flex-wrap">
          <div className="flex items-center gap-2">
            <Link2 size={16} className="text-faint" />
            <h2 className="m-0 text-[14px] font-semibold">{t('admin.refresh.title')}</h2>
          </div>
          {connected !== null && (
            <Badge variant={connected ? 'default' : 'destructive'}>
              {connected ? t('admin.refresh.extensionOn') : t('admin.refresh.extensionOff')}
            </Badge>
          )}
        </div>
        <p className="m-0 text-[13px] text-muted-foreground max-w-2xl">{t('admin.refresh.hint')}</p>

        <div className="flex flex-wrap items-end gap-3">
          <label className="flex flex-col gap-1.5 min-w-[280px] flex-1">
            <span className="text-[13px] font-medium text-muted-foreground">{t('admin.refresh.project')}</span>
            <select
              value={selected}
              onChange={e => { setSelected(e.target.value); setResult(null) }}
              disabled={!projects || projects.length === 0}
              className="h-9 rounded-lg border border-border bg-surface px-2 text-[13px] outline-none focus:border-primary disabled:opacity-50"
            >
              {projects === null && <option value="">…</option>}
              {projects?.length === 0 && <option value="">{t('admin.refresh.noProjects')}</option>}
              {projects?.map(p => (
                <option key={p.id} value={p.id} style={{ background: 'var(--card)' }}>
                  {p.name} — {p.id.slice(0, 8)}
                </option>
              ))}
            </select>
          </label>
          <Button disabled={!selected || busy || connected === false} onClick={refresh}>
            {busy ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />}
            {t('admin.refresh.run')}
          </Button>
        </div>

        {connected === false && (
          <p className="m-0 text-[13px]" style={{ color: 'var(--red)' }}>{t('admin.refresh.needExtension')}</p>
        )}

        {result && (
          <div className="rounded-lg border px-3 py-2.5 text-[13px]"
               style={{ borderColor: 'rgb(61 220 151 / 0.3)', background: 'rgb(61 220 151 / 0.07)' }}>
            {t('admin.refresh.done', { refreshed: result.refreshed, found: result.found })}
            {result.note && <div className="mt-1 text-muted-foreground">{result.note}</div>}
          </div>
        )}
      </section>
    </div>
  )
}
