import { useState, useEffect } from 'react'
import { BrowserRouter, NavLink, Routes, Route, useLocation, useSearchParams } from 'react-router-dom'
import { LayoutDashboard, FolderOpen, Film, ScrollText, BookOpen, ChevronRight, Languages, Cpu, Plug, Shield } from 'lucide-react'
import { TooltipProvider } from '@/components/ui/tooltip'
import { WebSocketProvider } from './api/WebSocketContext'
import { useWebSocketContext } from './api/useWebSocketContext'
import { LanguageProvider } from './i18n/LanguageContext'
import { useTranslation } from './i18n/useTranslation'
import { LANGS, LANG_LABELS, type Lang } from './i18n/translations'
import type { TranslationKey } from './i18n/translations'
import { fetchAPI } from './api/client'
import { useMe } from './api/useMe'
import { ApiKeyGate, ApiKeyStatus } from './components/ApiKeyGate'
import { BrandMark } from './components/BrandMark'
import type { Project } from './types'
import DashboardPage from './pages/DashboardPage'
import ProjectsPage from './pages/ProjectsPage'
import LogsPage from './pages/LogsPage'
import GalleryPage from './pages/GalleryPage'
import GuidePage from './pages/GuidePage'
import AdminPage from './pages/AdminPage'

const NAV: { to: string; icon: typeof LayoutDashboard; labelKey: TranslationKey; exact: boolean; adminOnly?: boolean }[] = [
  { to: '/', icon: LayoutDashboard, labelKey: 'nav.dashboard', exact: true },
  { to: '/projects', icon: FolderOpen, labelKey: 'nav.projects', exact: false },
  { to: '/gallery', icon: Film, labelKey: 'nav.gallery', exact: false },
  { to: '/logs', icon: ScrollText, labelKey: 'nav.logs', exact: false },
  { to: '/guide', icon: BookOpen, labelKey: 'nav.guide', exact: false },
  { to: '/admin', icon: Shield, labelKey: 'nav.admin', exact: false, adminOnly: true },
]

const BREADCRUMB_TAB_KEY: Record<string, TranslationKey> = {
  overview: 'app.breadcrumbTab.overview',
  characters: 'app.breadcrumbTab.characters',
  videos: 'app.breadcrumbTab.videos',
  pipeline: 'app.breadcrumbTab.pipeline',
}

function useBreadcrumbs() {
  const { t } = useTranslation()
  const loc = useLocation()
  const [searchParams] = useSearchParams()
  // The header sits outside <Routes>, so read the project id from the path.
  const id = loc.pathname.match(/^\/projects\/([^/]+)/)?.[1]
  const [project, setProject] = useState<{ id: string; name: string } | null>(null)

  useEffect(() => {
    if (!id) return
    fetchAPI<Project>(`/api/projects/${id}`).then(p => setProject({ id, name: p.name })).catch(() => setProject(null))
  }, [id])

  const crumbs: string[] = []
  if (loc.pathname === '/') crumbs.push(t('app.breadcrumb.dashboard'))
  else if (loc.pathname.startsWith('/projects')) {
    crumbs.push(t('app.breadcrumb.projects'))
    if (id) {
      crumbs.push(project?.id === id ? project.name : '…')
      const tab = searchParams.get('tab')
      const tabKey = tab ? BREADCRUMB_TAB_KEY[tab] : undefined
      if (tabKey) crumbs.push(t(tabKey))
    }
  } else if (loc.pathname.startsWith('/gallery')) crumbs.push(t('app.breadcrumb.gallery'))
  else if (loc.pathname.startsWith('/logs')) crumbs.push(t('app.breadcrumb.logs'))
  else if (loc.pathname.startsWith('/guide')) crumbs.push(t('app.breadcrumb.guide'))
  else if (loc.pathname.startsWith('/admin')) crumbs.push(t('app.breadcrumb.admin'))

  return crumbs
}

function LanguageSwitcher() {
  const { t, lang, setLang } = useTranslation()
  return (
    <label className="flex items-center gap-2 rounded-lg px-2.5 h-8 text-[13px] border border-border bg-card surface-hover">
      <Languages size={14} className="text-faint shrink-0" />
      <span className="sr-only">{t('app.language')}</span>
      <select
        value={lang}
        onChange={e => setLang(e.target.value as Lang)}
        className="flex-1 min-w-0 bg-transparent outline-none text-foreground"
      >
        {LANGS.map(l => (
          <option key={l} value={l} style={{ background: 'var(--card)' }}>{LANG_LABELS[l]}</option>
        ))}
      </select>
    </label>
  )
}

function StatusRow({ icon: Icon, label, value, tone }: { icon: typeof Cpu; label: string; value: string; tone: 'ok' | 'bad' | 'idle' }) {
  const color = tone === 'ok' ? 'var(--green)' : tone === 'bad' ? 'var(--red)' : 'var(--muted)'
  return (
    <div className="flex items-center gap-2 text-[13px]">
      <Icon size={14} className="text-faint shrink-0" />
      <span className="text-muted-foreground truncate">{label}</span>
      <span className="ml-auto flex items-center gap-1.5 font-medium tabular-nums" style={{ color }}>
        <span className="w-1.5 h-1.5 rounded-full" style={{ background: color }} />
        {value}
      </span>
    </div>
  )
}

function Sidebar() {
  const { t } = useTranslation()
  const { me } = useMe()
  const { worker } = useWebSocketContext()
  const [health, setHealth] = useState<{ extension_connected: boolean } | null>(null)

  useEffect(() => {
    fetchAPI<{ extension_connected: boolean }>('/health').then(setHealth).catch(() => setHealth(null))
  }, [])

  return (
    <aside className="w-60 flex-shrink-0 flex flex-col border-r border-border bg-surface">
      <div className="px-5 h-16 flex items-center gap-3">
        <BrandMark size={30} />
        <div className="flex flex-col leading-tight">
          <span className="text-[15px] font-semibold tracking-[-0.01em]">{t('app.brandName')}</span>
          <span className="text-xs text-faint">{t('app.brandTag')}</span>
        </div>
      </div>

      <nav className="flex flex-col gap-1 px-3 pt-2">
        {NAV.filter(item => !item.adminOnly || me?.is_admin).map(({ to, icon: Icon, labelKey, exact }) => (
          <NavLink
            key={to}
            to={to}
            end={exact}
            className={({ isActive }) =>
              `group flex items-center gap-3 px-3 h-9 rounded-lg text-[14px] font-medium transition-colors ${
                isActive
                  ? 'bg-accent-soft text-foreground'
                  : 'text-muted-foreground hover:bg-card-hover hover:text-foreground'
              }`
            }
          >
            {({ isActive }) => (
              <>
                <Icon size={17} strokeWidth={isActive ? 2.2 : 1.8} className={isActive ? 'text-brand' : 'text-faint group-hover:text-muted-foreground'} />
                {t(labelKey)}
              </>
            )}
          </NavLink>
        ))}
      </nav>

      <div className="mt-auto p-3 flex flex-col gap-3">
        <div className="rounded-xl border border-border bg-card p-3 flex flex-col gap-2.5">
          <StatusRow
            icon={Plug}
            label={t('app.extension')}
            value={health?.extension_connected ? t('app.extensionConnected') : health ? t('app.extensionDisconnected') : t('app.extensionChecking')}
            tone={health?.extension_connected ? 'ok' : health ? 'bad' : 'idle'}
          />
          <StatusRow
            icon={Cpu}
            label={t('app.workers')}
            value={worker ? `${worker.active}/${worker.active + worker.slots}` : '—'}
            tone={worker && worker.active > 0 ? 'ok' : 'idle'}
          />
        </div>
        <LanguageSwitcher />
        <ApiKeyStatus />
      </div>
    </aside>
  )
}

function Header() {
  const { t } = useTranslation()
  const { isConnected } = useWebSocketContext()
  const crumbs = useBreadcrumbs()

  return (
    <header className="flex items-center gap-4 px-8 h-16 flex-shrink-0 border-b border-border bg-background/75 backdrop-blur-md">
      <nav aria-label="Breadcrumb" className="flex items-center gap-1.5 text-[14px] min-w-0">
        {crumbs.map((c, i) => (
          <span key={i} className="flex items-center gap-1.5 min-w-0">
            {i > 0 && <ChevronRight size={14} className="text-faint shrink-0" />}
            <span className={`truncate ${i === crumbs.length - 1 ? 'text-foreground font-semibold' : 'text-muted-foreground'}`}>{c}</span>
          </span>
        ))}
      </nav>
      <span className="ml-auto" />
      <span
        className="flex items-center gap-2 h-8 px-3 rounded-full border text-[13px] font-medium"
        style={{
          borderColor: isConnected ? 'rgb(61 220 151 / 0.25)' : 'rgb(255 107 107 / 0.25)',
          background: isConnected ? 'rgb(61 220 151 / 0.08)' : 'rgb(255 107 107 / 0.08)',
          color: isConnected ? 'var(--green)' : 'var(--red)',
        }}
      >
        <span
          className="w-2 h-2 rounded-full"
          style={{ background: isConnected ? 'var(--green)' : 'var(--red)', animation: isConnected ? 'pulse 2s ease-in-out infinite' : 'none' }}
        />
        {isConnected ? t('app.wsLive') : t('app.wsDisconnected')}
      </span>
    </header>
  )
}

function Layout() {
  return (
    <div className="flex h-screen overflow-hidden bg-background text-foreground">
      <Sidebar />
      <div className="flex flex-col flex-1 min-w-0 overflow-hidden">
        <Header />
        <main className="flex-1 overflow-auto">
          <div className="mx-auto w-full max-w-[1320px] px-8 py-7">
            <Routes>
              <Route path="/" element={<DashboardPage />} />
              <Route path="/projects" element={<ProjectsPage />} />
              <Route path="/projects/:id" element={<ProjectsPage />} />
              <Route path="/gallery" element={<GalleryPage />} />
              <Route path="/logs" element={<LogsPage />} />
              <Route path="/guide" element={<GuidePage />} />
              <Route path="/admin" element={<AdminPage />} />
            </Routes>
          </div>
        </main>
      </div>
    </div>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <LanguageProvider>
        <ApiKeyGate>
          <WebSocketProvider>
            <TooltipProvider>
              <Layout />
            </TooltipProvider>
          </WebSocketProvider>
        </ApiKeyGate>
      </LanguageProvider>
    </BrowserRouter>
  )
}
