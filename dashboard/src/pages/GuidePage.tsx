import { useState, useEffect, useMemo } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Check, Copy, Search } from 'lucide-react'
import { fetchAPI } from '../api/client'
import { useTranslation } from '../i18n/useTranslation'
import type { TranslationKey } from '../i18n/translations'
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '../components/ui/card'
import { Badge } from '../components/ui/badge'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '../components/ui/tabs'
import { SKILL_CATEGORIES, WORKFLOW, type SkillGuide, type SkillStatus } from './guide/skills'

interface HealthResponse {
  status: string
  version: string
  extension_connected: boolean
  ws: {
    connected: boolean
    active_connections: number
    authenticated_connections: number
    connects: number
    disconnects: number
    uptime_s: number | null
  }
}

interface FlowStatus {
  transport: string
  flow_project_id: string | null
}

interface Me {
  auth_enabled: boolean
  name: string
  is_admin: boolean
}

function useStatusPoll() {
  const [health, setHealth] = useState<HealthResponse | null>(null)
  const [flow, setFlow] = useState<FlowStatus | null>(null)
  const [me, setMe] = useState<Me | null>(null)
  const [reachable, setReachable] = useState(true)

  useEffect(() => {
    let cancelled = false
    function poll() {
      fetchAPI<HealthResponse>('/health')
        .then(h => {
          if (cancelled) return
          setHealth(h)
          setReachable(true)
          fetchAPI<FlowStatus>('/api/flow/status').then(f => { if (!cancelled) setFlow(f) }).catch(() => {})
          fetchAPI<Me>('/api/auth/me').then(m => { if (!cancelled) setMe(m) }).catch(() => {})
        })
        .catch(() => { if (!cancelled) { setHealth(null); setReachable(false) } })
    }
    Promise.resolve().then(poll)
    const id = setInterval(poll, 4000)
    return () => { cancelled = true; clearInterval(id) }
  }, [])

  return { health, flow, me, reachable }
}

const SETUP_STEPS: { titleKey: TranslationKey; bodyKey: TranslationKey; commands?: string[] }[] = [
  { titleKey: 'guide.step1.title', bodyKey: 'guide.step1.body', commands: ['chrome://extensions'] },
  { titleKey: 'guide.step2.title', bodyKey: 'guide.step2.body', commands: ['https://flow.google.com/'] },
  { titleKey: 'guide.step3.title', bodyKey: 'guide.step3.body', commands: ['FLOW_PROJECT_ID=<flow-project-uuid>'] },
  {
    titleKey: 'guide.step4.title',
    bodyKey: 'guide.step4.body',
    commands: ['pip install -r requirements.txt', 'cp .env.example .env', 'python -m agent.main'],
  },
  { titleKey: 'guide.step5.title', bodyKey: 'guide.step5.body', commands: ['python setup.py', 'python setup.py sync'] },
  {
    titleKey: 'guide.step6.title',
    bodyKey: 'guide.step6.body',
    commands: ['curl -s http://127.0.0.1:8100/health', 'curl -s http://127.0.0.1:8100/api/flow/status'],
  },
]

const KEY_STEPS: { bodyKey: TranslationKey; commands: string[] }[] = [
  { bodyKey: 'guide.keys.step1', commands: ['AUTH_ENABLED=1', 'ADMIN_API_KEY=<long random string>'] },
  { bodyKey: 'guide.keys.step2', commands: ['python -m agent.users create alice --project <flow-project-uuid>'] },
  { bodyKey: 'guide.keys.step3', commands: ['curl -H "X-API-Key: fk_…" http://127.0.0.1:8100/api/auth/me'] },
  { bodyKey: 'guide.keys.step4', commands: ['python -m agent.users list', 'python -m agent.users rotate-key alice'] },
]

const TROUBLE_COUNT = 10

const STATUS_COLOR: Record<SkillStatus, string> = {
  unavailable: 'var(--red)',
  legacy: 'var(--yellow)',
  admin: 'var(--accent)',
}

const TABS = ['start', 'workflow', 'skills', 'trouble', 'server'] as const
type Tab = (typeof TABS)[number]

const FIRST_VIDEO = ['fk-create-project', 'fk-gen-refs', 'fk-gen-images', 'fk-gen-videos', 'fk-gen-narrator', 'fk-review-board', 'fk-concat-fit-narrator']

function useMe() {
  const [me, setMe] = useState<{ auth_enabled: boolean; name: string; is_admin: boolean; project_ids: string[] | null } | null>(null)
  useEffect(() => {
    fetchAPI<typeof me>('/api/auth/me').then(setMe).catch(() => setMe(null))
  }, [])
  return me
}

function CommandLine({ command }: { command: string }) {
  const { t } = useTranslation()
  const [copied, setCopied] = useState(false)

  const copy = () => {
    navigator.clipboard?.writeText(command).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    }).catch(() => {})
  }

  return (
    <div className="flex items-center gap-2 rounded px-2.5 py-1.5" style={{ background: 'var(--bg)', border: '1px solid var(--border)' }}>
      <code className="flex-1 min-w-0 overflow-x-auto whitespace-pre text-[11px] font-mono" style={{ color: 'var(--text)' }}>{command}</code>
      <button
        type="button"
        onClick={copy}
        title={copied ? t('guide.skills.copied') : t('guide.skills.copy')}
        aria-label={copied ? t('guide.skills.copied') : t('guide.skills.copy')}
        className="flex-shrink-0 hover:opacity-80"
        style={{ color: copied ? 'var(--green)' : 'var(--muted)' }}
      >
        {copied ? <Check size={12} /> : <Copy size={12} />}
      </button>
    </div>
  )
}

function StatusCard() {
  const { t } = useTranslation()
  const { health, flow, me, reachable } = useStatusPoll()

  const dot = (ok: boolean | null) => (
    <span className="w-1.5 h-1.5 rounded-full" style={{ background: ok === null ? 'var(--muted)' : ok ? 'var(--green)' : 'var(--red)' }} />
  )

  return (
    <Card className="py-4">
      <CardHeader>
        <CardTitle className="text-xs tracking-widest uppercase">{t('guide.status.title')}</CardTitle>
        <CardDescription className="text-[11px]">{t('guide.status.desc')}</CardDescription>
      </CardHeader>
      <CardContent>
        {!reachable ? (
          <div className="flex items-center gap-2 text-xs" style={{ color: 'var(--red)' }}>
            {dot(false)}
            {t('guide.status.unreachable')}
          </div>
        ) : !health ? (
          <div className="text-xs" style={{ color: 'var(--muted)' }}>{t('guide.status.checking')}</div>
        ) : (
          <div className="flex flex-wrap gap-x-6 gap-y-2.5 text-xs">
            <div className="flex items-center gap-2">
              {dot(true)}
              <span style={{ color: 'var(--text)' }}>{t('guide.status.agentRunning')}</span>
              <Badge variant="outline">v{health.version}</Badge>
            </div>
            <div className="flex items-center gap-2" style={{ color: health.extension_connected ? 'var(--green)' : 'var(--red)' }}>
              {dot(health.extension_connected)}
              {health.extension_connected ? t('guide.status.extensionConnected') : t('guide.status.extensionDisconnected')}
            </div>
            {flow && (
              <div className="flex items-center gap-2" style={{ color: 'var(--muted)' }}>
                {dot(Boolean(flow.flow_project_id))}
                {flow.flow_project_id
                  ? t('guide.status.flowProject', { id: flow.flow_project_id.slice(0, 8) })
                  : t('guide.status.noFlowProject')}
                <Badge variant="outline">{flow.transport}</Badge>
              </div>
            )}
            {me && (
              <div className="flex items-center gap-2" style={{ color: 'var(--muted)' }}>
                {dot(null)}
                {me.auth_enabled ? t('guide.status.signedInAs', { name: me.name }) : t('guide.status.authOff')}
                {me.auth_enabled && me.is_admin && <Badge variant="outline">{t('guide.status.admin')}</Badge>}
              </div>
            )}
            <div className="flex items-center gap-2" style={{ color: 'var(--muted)' }}>
              {dot(health.ws.authenticated_connections > 0 ? true : null)}
              {t('guide.status.ws', { active: health.ws.active_connections, authenticated: health.ws.authenticated_connections })}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  )
}

function NumberedStep({ n, title, body, commands }: { n: number; title?: string; body: string; commands?: string[] }) {
  return (
    <div className="flex gap-3.5">
      <span
        className="flex-shrink-0 flex items-center justify-center rounded-full text-xs font-semibold"
        style={{ width: 22, height: 22, background: 'var(--accent)', color: 'var(--bg)' }}
      >
        {n}
      </span>
      <div className="flex flex-col gap-1.5 min-w-0 flex-1">
        {title && <span className="text-xs font-semibold" style={{ color: 'var(--text)' }}>{title}</span>}
        <span className="text-[11px] leading-relaxed" style={{ color: 'var(--muted)' }}>{body}</span>
        {commands?.map(c => <CommandLine key={c} command={c} />)}
      </div>
    </div>
  )
}

function ServerSetupTab() {
  const { t } = useTranslation()
  return (
    <div className="flex flex-col gap-3">
      <p className="text-[11px] m-0" style={{ color: 'var(--muted)' }}>{t('guide.server.intro')}</p>
      {SETUP_STEPS.map((s, i) => (
        <Card key={s.titleKey} className="py-4">
          <CardContent>
            <NumberedStep n={i + 1} title={t(s.titleKey)} body={t(s.bodyKey)} commands={s.commands} />
          </CardContent>
        </Card>
      ))}

      <Card className="py-4">
        <CardHeader>
          <CardTitle className="text-xs tracking-widest uppercase">{t('guide.keys.title')}</CardTitle>
          <CardDescription className="text-[11px]">{t('guide.keys.body')}</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex flex-col gap-3.5">
            {KEY_STEPS.map((s, i) => (
              <NumberedStep key={s.bodyKey} n={i + 1} body={t(s.bodyKey)} commands={s.commands} />
            ))}
            <p className="text-[11px] m-0 rounded px-2.5 py-2" style={{ color: 'var(--yellow)', border: '1px solid var(--border)' }}>
              {t('guide.keys.note')}
            </p>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}

function SkillChip({ name, onOpen }: { name: string; onOpen: (name: string) => void }) {
  return (
    <button
      type="button"
      onClick={() => onOpen(name)}
      className="text-[11px] font-mono px-2 py-0.5 rounded hover:opacity-80"
      style={{ background: 'var(--bg)', color: 'var(--accent)', border: '1px solid var(--border)' }}
    >
      /{name}
    </button>
  )
}

function WorkflowTab({ onOpenSkill }: { onOpenSkill: (name: string) => void }) {
  const { t, lang } = useTranslation()
  return (
    <div className="flex flex-col gap-3">
      <p className="text-[11px] m-0" style={{ color: 'var(--muted)' }}>{t('guide.workflow.intro')}</p>
      <Card className="py-4">
        <CardContent>
          <ol className="m-0 p-0 list-none flex flex-col">
            {WORKFLOW.map((step, i) => (
              <li key={step.skills.join()} className="flex gap-3.5">
                <div className="flex flex-col items-center">
                  <span
                    className="flex-shrink-0 flex items-center justify-center rounded-full text-xs font-semibold"
                    style={{ width: 22, height: 22, background: 'var(--accent)', color: 'var(--bg)' }}
                  >
                    {i + 1}
                  </span>
                  {i < WORKFLOW.length - 1 && <span className="flex-1 w-px my-1" style={{ background: 'var(--border)' }} />}
                </div>
                <div className="flex flex-col gap-1.5 pb-4 min-w-0">
                  <span className="text-xs font-semibold" style={{ color: 'var(--text)' }}>{step.title[lang]}</span>
                  <span className="text-[11px] leading-relaxed" style={{ color: 'var(--muted)' }}>{step.body[lang]}</span>
                  <div className="flex flex-wrap gap-1.5">
                    {step.skills.map(name => <SkillChip key={name} name={name} onOpen={onOpenSkill} />)}
                  </div>
                </div>
              </li>
            ))}
          </ol>
        </CardContent>
      </Card>
    </div>
  )
}

function SkillCard({ skill }: { skill: SkillGuide }) {
  const { t, lang } = useTranslation()
  const label = (text: string) => (
    <span className="text-[10px] tracking-widest uppercase" style={{ color: 'var(--muted)' }}>{text}</span>
  )

  return (
    <Card id={`skill-${skill.name}`} className="py-4">
      <CardContent>
        <div className="flex flex-col gap-2.5">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-xs font-semibold font-mono" style={{ color: 'var(--text)' }}>/{skill.name}</span>
            {skill.remote && (
              <span className="text-[10px] px-1.5 py-px rounded" style={{ color: 'var(--green)', border: '1px solid var(--green)' }}>
                {t('guide.skills.remote')}
              </span>
            )}
            {skill.status && (
              <span
                className="text-[10px] px-1.5 py-px rounded"
                style={{ color: STATUS_COLOR[skill.status], border: `1px solid ${STATUS_COLOR[skill.status]}` }}
              >
                {t(`guide.skills.status.${skill.status}` as TranslationKey)}
              </span>
            )}
          </div>
          <p className="text-[11px] leading-relaxed m-0" style={{ color: 'var(--text)' }}>{skill.summary[lang]}</p>

          <div className="flex flex-col gap-1">
            {label(t('guide.skills.when'))}
            <p className="text-[11px] leading-relaxed m-0" style={{ color: 'var(--muted)' }}>{skill.when[lang]}</p>
          </div>

          <div className="flex flex-col gap-1">
            {label(t('guide.skills.usage'))}
            {skill.usage.map(u => <CommandLine key={u} command={u} />)}
          </div>

          {skill.needs && (
            <div className="flex flex-wrap items-center gap-1.5">
              {label(t('guide.skills.needs'))}
              {skill.needs.map(n => <Badge key={n} variant="outline" className="font-mono text-[10px]">{n}</Badge>)}
            </div>
          )}

          {skill.tips && (
            <div className="flex flex-col gap-1">
              {label(t('guide.skills.tips'))}
              <ul className="m-0 pl-4 list-disc flex flex-col gap-1">
                {skill.tips.map(tip => (
                  <li key={tip.en} className="text-[11px] leading-relaxed" style={{ color: 'var(--muted)' }}>{tip[lang]}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  )
}

function GetStartedTab({ me, onOpenSkill }: { me: ReturnType<typeof useMe>; onOpenSkill: (name: string) => void }) {
  const { t } = useTranslation()
  const origin = window.location.origin
  const label = (text: string) => (
    <span className="text-[10px] tracking-widest uppercase" style={{ color: 'var(--muted)' }}>{text}</span>
  )
  const note = (text: string, color = 'var(--muted)') => (
    <p className="text-[11px] leading-relaxed m-0" style={{ color }}>{text}</p>
  )

  return (
    <div className="flex flex-col gap-3">
      <p className="text-[11px] m-0 leading-relaxed" style={{ color: 'var(--muted)' }}>{t('guide.start.intro')}</p>

      <Card className="py-4">
        <CardContent>
          <div className="flex flex-col gap-2">
            <NumberedStep n={1} title={t('guide.start.step1.title')} body={t('guide.start.step1.body')} />
            <div className="pl-9 flex flex-col gap-1">
              {me?.auth_enabled && note(t('guide.start.signedIn', { name: me.name }), 'var(--green)')}
              {me?.auth_enabled && me.project_ids && note(
                me.project_ids.length
                  ? t('guide.start.projects', { count: me.project_ids.length })
                  : t('guide.start.noProjects'),
                me.project_ids.length ? 'var(--muted)' : 'var(--yellow)',
              )}
            </div>
          </div>
        </CardContent>
      </Card>

      <Card className="py-4">
        <CardContent>
          <NumberedStep n={2} title={t('guide.start.step2.title')} body={t('guide.start.step2.body')}
            commands={['winget install --id Git.Git -e']} />
        </CardContent>
      </Card>

      <Card className="py-4">
        <CardContent>
          <div className="flex flex-col gap-2.5">
            <NumberedStep n={3} title={t('guide.start.step3.title')} body={t('guide.start.step3.body')} />
            <div className="pl-9 flex flex-col gap-2.5">
              <div className="flex flex-col gap-1">
                {label(t('guide.install.unix'))}
                <CommandLine command={`curl -fsSL ${origin}/install.sh | bash`} />
              </div>
              <div className="flex flex-col gap-1">
                {label(t('guide.install.windows'))}
                <CommandLine command={`irm ${origin}/install.ps1 | iex`} />
              </div>
              {note(t('guide.start.step3.where'))}
              {note(t('guide.install.update'))}
            </div>
          </div>
        </CardContent>
      </Card>

      <Card className="py-4">
        <CardContent>
          <NumberedStep n={4} title={t('guide.start.step4.title')} body={t('guide.start.step4.body')} commands={['/fk-status']} />
        </CardContent>
      </Card>

      <Card className="py-4">
        <CardContent>
          <div className="flex flex-col gap-2">
            <NumberedStep n={5} title={t('guide.start.step5.title')} body={t('guide.start.step5.body')} />
            <div className="pl-9 flex flex-wrap items-center gap-1.5">
              {FIRST_VIDEO.map((name, i) => (
                <span key={name} className="flex items-center gap-1.5">
                  {i > 0 && <span className="text-[11px]" style={{ color: 'var(--muted)' }}>→</span>}
                  <SkillChip name={name} onOpen={onOpenSkill} />
                </span>
              ))}
            </div>
            <div className="pl-9">{note(t('guide.start.step5.watch'))}</div>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}

function SkillsTab({ query, onQuery }: { query: string; onQuery: (q: string) => void }) {
  const { t, lang } = useTranslation()
  const needle = query.trim().toLowerCase().replace(/^\//, '')

  const categories = useMemo(() => SKILL_CATEGORIES
    .map(c => ({
      ...c,
      skills: c.skills.filter(s => !needle || [s.name, s.summary[lang], s.when[lang], s.summary.en]
        .some(text => text.toLowerCase().includes(needle))),
    }))
    .filter(c => c.skills.length > 0), [needle, lang])

  const total = categories.reduce((n, c) => n + c.skills.length, 0)

  return (
    <div className="flex flex-col gap-3">
      <p className="text-[11px] m-0 leading-relaxed" style={{ color: 'var(--muted)' }}>{t('guide.skills.intro')}</p>
      <div className="flex items-center gap-2 rounded px-2.5 py-1.5" style={{ background: 'var(--card)', border: '1px solid var(--border)' }}>
        <Search size={12} style={{ color: 'var(--muted)' }} />
        <input
          type="search"
          value={query}
          onChange={e => onQuery(e.target.value)}
          placeholder={t('guide.skills.search')}
          aria-label={t('guide.skills.search')}
          className="flex-1 min-w-0 bg-transparent outline-none text-xs"
          style={{ color: 'var(--text)' }}
        />
        <span className="text-[10px]" style={{ color: 'var(--muted)' }}>{t('guide.skills.count', { count: total })}</span>
      </div>

      {total === 0 && (
        <p className="text-xs m-0" style={{ color: 'var(--muted)' }}>{t('guide.skills.empty', { q: query })}</p>
      )}

      {categories.map(c => (
        <section key={c.id} className="flex flex-col gap-2.5">
          <h2 className="m-0 mt-2 text-[11px] tracking-widest uppercase font-semibold" style={{ color: 'var(--muted)' }}>{c.title[lang]}</h2>
          {c.skills.map(s => <SkillCard key={s.name} skill={s} />)}
        </section>
      ))}
    </div>
  )
}

function TroubleTab() {
  const { t } = useTranslation()
  return (
    <div className="flex flex-col gap-3">
      <p className="text-[11px] m-0" style={{ color: 'var(--muted)' }}>{t('guide.trouble.intro')}</p>
      <Card className="py-4">
        <CardContent>
          <div className="flex flex-col gap-3">
            {Array.from({ length: TROUBLE_COUNT }, (_, i) => i + 1).map(n => (
              <div
                key={n}
                className="flex flex-col gap-0.5 pb-3"
                style={{ borderBottom: n < TROUBLE_COUNT ? '1px solid var(--border)' : 'none' }}
              >
                <span className="text-xs font-semibold font-mono" style={{ color: 'var(--text)' }}>
                  {t(`guide.trouble${n}.problem` as TranslationKey)}
                </span>
                <span className="text-[11px] leading-relaxed" style={{ color: 'var(--muted)' }}>
                  {t(`guide.trouble${n}.solution` as TranslationKey)}
                </span>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  )
}

export default function GuidePage() {
  const { t } = useTranslation()
  const me = useMe()
  const [params, setParams] = useSearchParams()
  // Server setup is for whoever runs the agent; users who only have a key don't see it.
  const tabs = TABS.filter(id => id !== 'server' || !me || me.is_admin)
  const requested = params.get('tab') === 'setup' ? 'server' : params.get('tab')
  const tab: Tab = (tabs as readonly string[]).includes(requested ?? '') ? (requested as Tab) : 'start'
  const query = params.get('q') ?? ''

  const update = (next: { tab?: Tab; q?: string }) => {
    const p = new URLSearchParams(params)
    if (next.tab) p.set('tab', next.tab)
    if (next.q !== undefined) {
      if (next.q) p.set('q', next.q)
      else p.delete('q')
    }
    setParams(p, { replace: true })
  }

  const openSkill = (name: string) => {
    update({ tab: 'skills', q: name })
    // The page scrolls inside <main>, not the window.
    document.querySelector('main')?.scrollTo({ top: 0 })
  }

  return (
    <div className="flex flex-col gap-5 max-w-3xl">
      <div>
        <h1 className="m-0 text-lg font-semibold" style={{ color: 'var(--text)' }}>{t('guide.title')}</h1>
        <p className="text-[11px] mt-1 leading-relaxed" style={{ color: 'var(--muted)' }}>{t('guide.intro')}</p>
      </div>

      <StatusCard />

      <Tabs value={tab} onValueChange={v => update({ tab: v as Tab })}>
        <TabsList className="max-w-full overflow-x-auto">
          {tabs.map(id => (
            <TabsTrigger key={id} value={id}>{t(`guide.tab.${id}` as TranslationKey)}</TabsTrigger>
          ))}
        </TabsList>
        <TabsContent value="start" className="pt-4"><GetStartedTab me={me} onOpenSkill={openSkill} /></TabsContent>
        {tabs.includes('server') && <TabsContent value="server" className="pt-4"><ServerSetupTab /></TabsContent>}
        <TabsContent value="workflow" className="pt-4"><WorkflowTab onOpenSkill={openSkill} /></TabsContent>
        <TabsContent value="skills" className="pt-4"><SkillsTab query={query} onQuery={q => update({ q })} /></TabsContent>
        <TabsContent value="trouble" className="pt-4"><TroubleTab /></TabsContent>
      </Tabs>
    </div>
  )
}
