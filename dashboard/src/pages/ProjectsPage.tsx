import { useState, useEffect } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { fetchAPI } from '../api/client'
import type { Project } from '../types'
import ProjectDetailPage from './ProjectDetailPage'
import { useTranslation } from '../i18n/useTranslation'
import type { TranslationKey } from '../i18n/translations'
import { Card, CardHeader, CardTitle, CardDescription, CardContent, CardAction, CardFooter } from '../components/ui/card'
import { Badge } from '../components/ui/badge'
import { Tabs, TabsList, TabsTrigger } from '../components/ui/tabs'
import { PageHeader, EmptyState } from '../components/layout/PageHeader'
import { FolderOpen } from 'lucide-react'

type FilterTab = 'ACTIVE' | 'ARCHIVED' | 'ALL'

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString()
}

function TierBadge({ tier, t }: { tier: string | null; t: (key: TranslationKey) => string }) {
  if (!tier) return null
  const isTwo = tier.includes('TWO')
  return <Badge variant={isTwo ? 'default' : 'secondary'}>{isTwo ? t('projects.tier2') : t('projects.tier1')}</Badge>
}

// A stable gradient per project, so cards are easy to tell apart at a glance.
const COVERS = [
  ['#6f78f7', '#3b2fb8'], ['#3ddc97', '#11695a'], ['#f5b945', '#9a4b12'],
  ['#ff6b9d', '#7a1f57'], ['#4cc9f0', '#1d4e89'], ['#b388ff', '#4a2a8a'],
]

function coverFor(id: string) {
  let h = 0
  for (const ch of id) h = (h * 31 + ch.charCodeAt(0)) >>> 0
  return COVERS[h % COVERS.length]
}

function ProjectCard({ project, onClick, t }: { project: Project; onClick: () => void; t: (key: TranslationKey, params?: Record<string, string | number>) => string }) {
  const [from, to] = coverFor(project.id)
  return (
    <Card className="pt-0 gap-4 h-full cursor-pointer transition-all hover:border-border-strong hover:-translate-y-0.5 hover:shadow-(--shadow-pop)" onClick={onClick}>
      <div
        className="relative h-24 flex items-end px-5 pb-3 border-b border-border"
        style={{ background: `radial-gradient(120% 140% at 0% 0%, ${from}55, transparent 60%), radial-gradient(120% 140% at 100% 100%, ${to}66, transparent 55%), var(--surface)` }}
      >
        <span className="w-10 h-10 rounded-xl flex items-center justify-center text-[17px] font-semibold text-white uppercase" style={{ background: `linear-gradient(135deg, ${from}, ${to})`, boxShadow: '0 0 0 1px rgb(255 255 255 / 0.15) inset' }}>
          {project.name.slice(0, 1)}
        </span>
      </div>
      <CardHeader>
        <CardTitle className="text-[15px]">{project.name}</CardTitle>
        {project.description && (
          <CardDescription className="text-[13px] leading-relaxed line-clamp-2">{project.description}</CardDescription>
        )}
        <CardAction>
          <TierBadge tier={project.user_paygate_tier} t={t} />
        </CardAction>
      </CardHeader>
      <CardContent>
        <div className="flex flex-wrap gap-1.5">
          {project.material && <Badge variant="outline">{project.material}</Badge>}
          <Badge variant="outline">{project.status}</Badge>
        </div>
      </CardContent>
      <CardFooter>
        <span className="text-xs tracking-wide" style={{ color: 'var(--muted)' }}>{t('projects.footer', { date: formatDate(project.created_at), id: project.id.slice(0, 8) })}</span>
      </CardFooter>
    </Card>
  )
}

export default function ProjectsPage() {
  const { t } = useTranslation()
  const { id } = useParams<{ id?: string }>()
  const navigate = useNavigate()
  const [tab, setTab] = useState<FilterTab>('ACTIVE')
  const [projects, setProjects] = useState<Project[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetchAPI<Project[]>('/api/projects')
      .then(setProjects)
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [])

  // If there's an :id param, show detail page
  if (id) {
    return <ProjectDetailPage projectId={id} onBack={() => navigate('/projects')} />
  }

  const filtered = projects.filter(p => {
    if (tab === 'ALL') return p.status !== 'DELETED'
    return p.status === tab
  })

  return (
    <div className="flex flex-col gap-4">
      <PageHeader title={t('projects.title')} description={t('projects.description')}>
        <div className="flex items-center gap-3">
          <Tabs value={tab} onValueChange={v => setTab(v as FilterTab)}>
            <TabsList>
              <TabsTrigger value="ACTIVE">{t('projects.tab.active')}</TabsTrigger>
              <TabsTrigger value="ARCHIVED">{t('projects.tab.archived')}</TabsTrigger>
              <TabsTrigger value="ALL">{t('projects.tab.all')}</TabsTrigger>
            </TabsList>
          </Tabs>
          <span className="ml-auto text-[13px]" style={{ color: 'var(--muted)' }}>{t('projects.count', { n: filtered.length })}</span>
        </div>
      </PageHeader>

      {loading ? (
        <div className="text-[13px]" style={{ color: 'var(--muted)' }}>{t('projects.loading')}</div>
      ) : filtered.length === 0 ? (
        <Card><EmptyState icon={FolderOpen} title={t(`projects.empty.${tab}` as TranslationKey)} /></Card>
      ) : (
        <div className="grid gap-4" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))' }}>
          {filtered.map(p => (
            <ProjectCard key={p.id} project={p} onClick={() => navigate(`/projects/${p.id}`)} t={t} />
          ))}
        </div>
      )}
    </div>
  )
}
