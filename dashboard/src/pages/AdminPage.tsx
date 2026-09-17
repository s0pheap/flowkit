import { useCallback, useEffect, useState, type FormEvent } from 'react'
import {
  Check, Copy, KeyRound, Loader2, Plus, RefreshCw, ShieldAlert, ShieldCheck,
  Sliders, Trash2, UserPlus, Users, Wrench, X,
} from 'lucide-react'

import { fetchAPI } from '../api/client'
import { useMe } from '../api/useMe'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { EmptyState, PageHeader } from '../components/layout/PageHeader'
import { ModelsPanel } from '../components/admin/ModelsPanel'
import { MaintenancePanel } from '../components/admin/MaintenancePanel'
import { useTranslation } from '../i18n/useTranslation'

type AdminUser = {
  id: string
  name: string
  key_prefix: string
  is_admin: boolean
  disabled: boolean
  project_ids: string[]
  created_at: string
  last_used_at: string | null
}

type PoolItem = {
  flow_project_id: string
  assigned_to_user: string | null
  assigned_at: string | null
  notes: string | null
  created_at: string
}

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

function shortDate(value: string | null): string {
  if (!value) return '—'
  const d = new Date(value)
  return Number.isNaN(d.getTime()) ? value : d.toLocaleDateString()
}

/** A freshly minted key, shown once. The server keeps only its hash. */
function SecretBanner({ secret, onDismiss }: { secret: string; onDismiss: () => void }) {
  const { t } = useTranslation()
  const [copied, setCopied] = useState(false)

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(secret)
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    } catch {
      // Clipboard blocked (insecure origin, or the user said no) — the key is on screen to select.
    }
  }

  return (
    <div className="flex flex-col gap-3 rounded-xl border p-4 mb-5"
         style={{ borderColor: 'rgb(61 220 151 / 0.3)', background: 'rgb(61 220 151 / 0.07)' }}>
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-2 min-w-0">
          <KeyRound size={16} style={{ color: 'var(--green)' }} className="shrink-0" />
          <span className="text-[14px] font-semibold">{t('admin.keyOnce.title')}</span>
        </div>
        <Button variant="ghost" size="sm" onClick={onDismiss} aria-label={t('common.close')}>
          <X size={15} />
        </Button>
      </div>
      <p className="m-0 text-[13px] text-muted-foreground">{t('admin.keyOnce.hint')}</p>
      <div className="flex items-center gap-2 rounded-lg border border-border bg-surface px-3 h-10">
        <code className="flex-1 min-w-0 truncate text-[13px] font-mono">{secret}</code>
        <Button variant="outline" size="sm" onClick={copy}>
          {copied ? <Check size={14} /> : <Copy size={14} />}
          {copied ? t('admin.copied') : t('admin.copy')}
        </Button>
      </div>
    </div>
  )
}

function ErrorLine({ message }: { message: string | null }) {
  if (!message) return null
  return <p className="m-0 mb-4 text-[13px]" style={{ color: 'var(--red)' }}>{message}</p>
}

// ─── Users ───────────────────────────────────────────────────

function UsersPanel({ onSecret, onError }: { onSecret: (s: string) => void; onError: (e: string | null) => void }) {
  const { t } = useTranslation()
  const [users, setUsers] = useState<AdminUser[] | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [name, setName] = useState('')
  const [isAdmin, setIsAdmin] = useState(false)
  const [projects, setProjects] = useState('')
  const [grantFor, setGrantFor] = useState<string | null>(null)
  const [grantValue, setGrantValue] = useState('')

  const load = useCallback(async () => {
    try {
      setUsers(await fetchAPI<AdminUser[]>('/api/admin/users'))
    } catch (e) {
      onError(e instanceof Error ? e.message : String(e))
    }
  }, [onError])

  useEffect(() => { void load() }, [load])

  const act = async (id: string, run: () => Promise<unknown>) => {
    setBusy(id)
    onError(null)
    try {
      await run()
      await load()
    } catch (e) {
      onError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(null)
    }
  }

  const create = async (e: FormEvent) => {
    e.preventDefault()
    const trimmed = name.trim()
    if (!trimmed) return
    const ids = projects.split(/[\s,]+/).map(s => s.trim()).filter(Boolean)
    const bad = ids.find(id => !UUID.test(id))
    if (bad) {
      onError(t('admin.users.badUuid', { value: bad }))
      return
    }
    await act('new', async () => {
      const res = await fetchAPI<{ api_key: string }>('/api/admin/users', {
        method: 'POST',
        body: JSON.stringify({ name: trimmed, is_admin: isAdmin, project_ids: ids }),
      })
      onSecret(res.api_key)
      setName('')
      setIsAdmin(false)
      setProjects('')
    })
  }

  const grant = async (e: FormEvent, uid: string) => {
    e.preventDefault()
    const id = grantValue.trim()
    if (!UUID.test(id)) {
      onError(t('admin.users.badUuid', { value: id || '—' }))
      return
    }
    await act(uid, async () => {
      await fetchAPI(`/api/admin/users/${uid}/projects`, {
        method: 'POST',
        body: JSON.stringify({ project_id: id }),
      })
      setGrantFor(null)
      setGrantValue('')
    })
  }

  return (
    <div className="flex flex-col gap-6">
      <form onSubmit={create} className="flex flex-wrap items-end gap-3 rounded-xl border border-border bg-card p-4">
        <label className="flex flex-col gap-1.5 min-w-[160px] flex-1">
          <span className="text-[13px] font-medium text-muted-foreground">{t('admin.users.name')}</span>
          <input
            value={name}
            onChange={e => setName(e.target.value)}
            placeholder={t('admin.users.namePlaceholder')}
            className="h-9 rounded-lg border border-border bg-surface px-3 text-[14px] outline-none focus:border-primary transition-colors"
          />
        </label>
        <label className="flex flex-col gap-1.5 min-w-[240px] flex-[2]">
          <span className="text-[13px] font-medium text-muted-foreground">{t('admin.users.grants')}</span>
          <input
            value={projects}
            onChange={e => setProjects(e.target.value)}
            placeholder={t('admin.users.grantsPlaceholder')}
            className="h-9 rounded-lg border border-border bg-surface px-3 text-[13px] font-mono outline-none focus:border-primary transition-colors"
          />
        </label>
        <label className="flex items-center gap-2 h-9 text-[13px] cursor-pointer">
          <input type="checkbox" checked={isAdmin} onChange={e => setIsAdmin(e.target.checked)} />
          {t('admin.users.makeAdmin')}
        </label>
        <Button type="submit" disabled={!name.trim() || busy === 'new'}>
          {busy === 'new' ? <Loader2 size={14} className="animate-spin" /> : <UserPlus size={14} />}
          {t('admin.users.create')}
        </Button>
      </form>

      {users === null ? (
        <div className="flex justify-center py-10 text-faint"><Loader2 size={20} className="animate-spin" /></div>
      ) : users.length === 0 ? (
        <EmptyState icon={Users} title={t('admin.users.empty')} hint={t('admin.users.emptyHint')} />
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>{t('admin.users.name')}</TableHead>
              <TableHead>{t('admin.users.key')}</TableHead>
              <TableHead>{t('admin.users.grants')}</TableHead>
              <TableHead>{t('admin.users.lastUsed')}</TableHead>
              <TableHead className="text-right">{t('admin.users.actions')}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {users.map(u => (
              <TableRow key={u.id}>
                <TableCell>
                  <div className="flex items-center gap-2">
                    <span className="font-medium">{u.name}</span>
                    {u.is_admin && <Badge variant="default">{t('admin.users.admin')}</Badge>}
                    {u.disabled && <Badge variant="destructive">{t('admin.users.disabled')}</Badge>}
                  </div>
                </TableCell>
                <TableCell><code className="text-[12px] font-mono text-muted-foreground">{u.key_prefix}…</code></TableCell>
                <TableCell>
                  <div className="flex flex-wrap items-center gap-1.5">
                    {u.project_ids.length === 0 && <span className="text-[13px] text-faint">{t('common.dash')}</span>}
                    {u.project_ids.map(pid => (
                      <span key={pid} className="inline-flex items-center gap-1 rounded-md border border-border bg-surface px-1.5 py-0.5 text-[11px] font-mono">
                        {pid.slice(0, 8)}
                        <button
                          type="button"
                          aria-label={t('admin.users.revoke')}
                          title={t('admin.users.revoke')}
                          className="text-faint hover:text-destructive transition-colors"
                          onClick={() => act(u.id, () => fetchAPI(`/api/admin/users/${u.id}/projects/${pid}`, { method: 'DELETE' }))}
                        >
                          <X size={11} />
                        </button>
                      </span>
                    ))}
                    {grantFor === u.id ? (
                      <form onSubmit={e => grant(e, u.id)} className="flex items-center gap-1">
                        <input
                          autoFocus
                          value={grantValue}
                          onChange={e => setGrantValue(e.target.value)}
                          onBlur={() => { if (!grantValue.trim()) setGrantFor(null) }}
                          placeholder={t('admin.pool.uuidPlaceholder')}
                          className="h-6 w-[230px] rounded-md border border-border bg-surface px-1.5 text-[11px] font-mono outline-none focus:border-primary"
                        />
                        <Button type="submit" variant="ghost" size="sm"><Check size={12} /></Button>
                      </form>
                    ) : (
                      <Button variant="ghost" size="sm" onClick={() => { setGrantFor(u.id); setGrantValue('') }}>
                        <Plus size={12} />{t('admin.users.grant')}
                      </Button>
                    )}
                  </div>
                </TableCell>
                <TableCell className="text-[13px] text-muted-foreground">{shortDate(u.last_used_at)}</TableCell>
                <TableCell>
                  <div className="flex items-center justify-end gap-1">
                    {busy === u.id && <Loader2 size={13} className="animate-spin text-faint" />}
                    <Button
                      variant="ghost" size="sm" title={t('admin.users.rotate')}
                      onClick={() => act(u.id, async () => {
                        const res = await fetchAPI<{ api_key: string }>(`/api/admin/users/${u.id}/rotate-key`, { method: 'POST' })
                        onSecret(res.api_key)
                      })}
                    >
                      <RefreshCw size={13} />
                    </Button>
                    <Button
                      variant="ghost" size="sm"
                      title={u.is_admin ? t('admin.users.demote') : t('admin.users.promote')}
                      onClick={() => act(u.id, () => fetchAPI(`/api/admin/users/${u.id}`, {
                        method: 'PATCH', body: JSON.stringify({ is_admin: !u.is_admin }),
                      }))}
                    >
                      {u.is_admin ? <ShieldAlert size={13} /> : <ShieldCheck size={13} />}
                    </Button>
                    <Button
                      variant="ghost" size="sm"
                      title={u.disabled ? t('admin.users.enable') : t('admin.users.disable')}
                      onClick={() => act(u.id, () => fetchAPI(`/api/admin/users/${u.id}`, {
                        method: 'PATCH', body: JSON.stringify({ disabled: !u.disabled }),
                      }))}
                    >
                      {u.disabled ? <Check size={13} /> : <X size={13} />}
                    </Button>
                    <Button
                      variant="ghost" size="sm" title={t('admin.users.delete')}
                      onClick={() => {
                        if (!window.confirm(t('admin.users.confirmDelete', { name: u.name }))) return
                        void act(u.id, () => fetchAPI(`/api/admin/users/${u.id}`, { method: 'DELETE' }))
                      }}
                    >
                      <Trash2 size={13} className="text-destructive" />
                    </Button>
                  </div>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </div>
  )
}

// ─── Flow project pool ───────────────────────────────────────

function PoolPanel({ onError }: { onError: (e: string | null) => void }) {
  const { t } = useTranslation()
  const [pool, setPool] = useState<PoolItem[] | null>(null)
  const [users, setUsers] = useState<AdminUser[]>([])
  const [busy, setBusy] = useState<string | null>(null)
  const [uuid, setUuid] = useState('')
  const [notes, setNotes] = useState('')

  const load = useCallback(async () => {
    try {
      const [items, people] = await Promise.all([
        fetchAPI<PoolItem[]>('/api/flow-pool'),
        fetchAPI<AdminUser[]>('/api/admin/users'),
      ])
      setPool(items)
      setUsers(people)
    } catch (e) {
      onError(e instanceof Error ? e.message : String(e))
    }
  }, [onError])

  useEffect(() => { void load() }, [load])

  const act = async (id: string, run: () => Promise<unknown>) => {
    setBusy(id)
    onError(null)
    try {
      await run()
      await load()
    } catch (e) {
      onError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(null)
    }
  }

  const add = async (e: FormEvent) => {
    e.preventDefault()
    const id = uuid.trim()
    if (!UUID.test(id)) {
      onError(t('admin.users.badUuid', { value: id || '—' }))
      return
    }
    await act('new', async () => {
      await fetchAPI('/api/flow-pool', {
        method: 'POST',
        body: JSON.stringify({ flow_project_id: id, notes: notes.trim() || null }),
      })
      setUuid('')
      setNotes('')
    })
  }

  const nameFor = (uid: string) => users.find(u => u.id === uid)?.name ?? uid.slice(0, 8)

  return (
    <div className="flex flex-col gap-6">
      <p className="m-0 text-[13px] text-muted-foreground">{t('admin.pool.intro')}</p>

      <form onSubmit={add} className="flex flex-wrap items-end gap-3 rounded-xl border border-border bg-card p-4">
        <label className="flex flex-col gap-1.5 min-w-[280px] flex-1">
          <span className="text-[13px] font-medium text-muted-foreground">{t('admin.pool.uuid')}</span>
          <input
            value={uuid}
            onChange={e => setUuid(e.target.value)}
            placeholder={t('admin.pool.uuidPlaceholder')}
            className="h-9 rounded-lg border border-border bg-surface px-3 text-[13px] font-mono outline-none focus:border-primary transition-colors"
          />
        </label>
        <label className="flex flex-col gap-1.5 min-w-[160px] flex-1">
          <span className="text-[13px] font-medium text-muted-foreground">{t('admin.pool.notes')}</span>
          <input
            value={notes}
            onChange={e => setNotes(e.target.value)}
            placeholder={t('admin.pool.notesPlaceholder')}
            className="h-9 rounded-lg border border-border bg-surface px-3 text-[14px] outline-none focus:border-primary transition-colors"
          />
        </label>
        <Button type="submit" disabled={!uuid.trim() || busy === 'new'}>
          {busy === 'new' ? <Loader2 size={14} className="animate-spin" /> : <Plus size={14} />}
          {t('admin.pool.add')}
        </Button>
      </form>

      {pool === null ? (
        <div className="flex justify-center py-10 text-faint"><Loader2 size={20} className="animate-spin" /></div>
      ) : pool.length === 0 ? (
        <EmptyState icon={KeyRound} title={t('admin.pool.empty')} hint={t('admin.pool.emptyHint')} />
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>{t('admin.pool.uuid')}</TableHead>
              <TableHead>{t('admin.pool.assignedTo')}</TableHead>
              <TableHead>{t('admin.pool.notes')}</TableHead>
              <TableHead className="text-right">{t('admin.users.actions')}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {pool.map(item => (
              <TableRow key={item.flow_project_id}>
                <TableCell><code className="text-[12px] font-mono">{item.flow_project_id}</code></TableCell>
                <TableCell>
                  {item.assigned_to_user ? (
                    <Badge variant="secondary">{nameFor(item.assigned_to_user)}</Badge>
                  ) : (
                    <select
                      defaultValue=""
                      className="h-8 rounded-lg border border-border bg-surface px-2 text-[13px] outline-none focus:border-primary"
                      onChange={e => {
                        const uid = e.target.value
                        if (!uid) return
                        void act(item.flow_project_id, () => fetchAPI(`/api/flow-pool/${item.flow_project_id}/assign`, {
                          method: 'POST', body: JSON.stringify({ user_id: uid }),
                        }))
                      }}
                    >
                      <option value="" style={{ background: 'var(--card)' }}>{t('admin.pool.assign')}</option>
                      {users.map(u => (
                        <option key={u.id} value={u.id} style={{ background: 'var(--card)' }}>{u.name}</option>
                      ))}
                    </select>
                  )}
                </TableCell>
                <TableCell className="text-[13px] text-muted-foreground">{item.notes || t('common.dash')}</TableCell>
                <TableCell>
                  <div className="flex items-center justify-end gap-1">
                    {busy === item.flow_project_id && <Loader2 size={13} className="animate-spin text-faint" />}
                    {item.assigned_to_user && (
                      <Button
                        variant="ghost" size="sm" title={t('admin.pool.unassign')}
                        onClick={() => act(item.flow_project_id, () =>
                          fetchAPI(`/api/flow-pool/${item.flow_project_id}/unassign`, { method: 'POST' }))}
                      >
                        {t('admin.pool.unassign')}
                      </Button>
                    )}
                    <Button
                      variant="ghost" size="sm" title={t('admin.pool.remove')}
                      onClick={() => {
                        if (!window.confirm(t('admin.pool.confirmRemove', { id: item.flow_project_id.slice(0, 8) }))) return
                        void act(item.flow_project_id, () =>
                          fetchAPI(`/api/flow-pool/${item.flow_project_id}`, { method: 'DELETE' }))
                      }}
                    >
                      <Trash2 size={13} className="text-destructive" />
                    </Button>
                  </div>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </div>
  )
}

// ─── Page ────────────────────────────────────────────────────

export default function AdminPage() {
  const { t } = useTranslation()
  const { me, loading } = useMe()
  const [secret, setSecret] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  if (loading) {
    return <div className="flex justify-center py-16 text-faint"><Loader2 size={22} className="animate-spin" /></div>
  }

  // The API refuses these routes to non-admins anyway; this just explains why the page is bare.
  if (!me?.is_admin) {
    return (
      <>
        <PageHeader title={t('admin.title')} description={t('admin.description')} />
        <EmptyState icon={ShieldAlert} title={t('admin.denied')} hint={t('admin.deniedHint')} />
      </>
    )
  }

  return (
    <>
      <PageHeader title={t('admin.title')} description={t('admin.description')} />
      {secret && <SecretBanner secret={secret} onDismiss={() => setSecret(null)} />}
      <ErrorLine message={error} />
      <Tabs defaultValue="users">
        <TabsList className="mb-5">
          <TabsTrigger value="users"><Users size={14} />{t('admin.tab.users')}</TabsTrigger>
          <TabsTrigger value="pool"><KeyRound size={14} />{t('admin.tab.pool')}</TabsTrigger>
          <TabsTrigger value="models"><Sliders size={14} />{t('admin.tab.models')}</TabsTrigger>
          <TabsTrigger value="maintenance"><Wrench size={14} />{t('admin.tab.maintenance')}</TabsTrigger>
        </TabsList>
        <TabsContent value="users">
          <UsersPanel onSecret={setSecret} onError={setError} />
        </TabsContent>
        <TabsContent value="pool">
          <PoolPanel onError={setError} />
        </TabsContent>
        <TabsContent value="models">
          <ModelsPanel onError={setError} />
        </TabsContent>
        <TabsContent value="maintenance">
          <MaintenancePanel onError={setError} />
        </TabsContent>
      </Tabs>
    </>
  )
}
