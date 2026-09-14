import { useCallback, useEffect, useState } from 'react'
import { fetchAPI } from '../../api/client'
import { useTranslation } from '../../i18n/useTranslation'
import { Card, CardHeader, CardTitle, CardContent } from '../ui/card'
import { Button } from '../ui/button'
import { Progress } from '../ui/progress'

interface RenderJob {
  status: 'none' | 'queued' | 'running' | 'done' | 'failed'
  step?: string
  done_steps?: number
  total_steps?: number
  error?: string | null
  duration?: number | null
  size_bytes?: number | null
  captions_url?: string | null
  warnings?: string[]
  finished_at?: number | null
}

type SubsMode = 'soft' | 'burn' | 'none'

/** The server-side final cut for one video: start a render, follow it, watch and download the result. */
export default function FinalVideoPanel({ videoId, title }: { videoId: string; title: string }) {
  const { t } = useTranslation()
  const [job, setJob] = useState<RenderJob | null>(null)
  const [token, setToken] = useState<string | null>(null)
  const [subs, setSubs] = useState<SubsMode>('soft')
  const [error, setError] = useState<string | null>(null)
  const [starting, setStarting] = useState(false)

  const load = useCallback(async () => {
    try {
      setJob(await fetchAPI<RenderJob>(`/api/videos/${videoId}/render`))
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }, [videoId])

  useEffect(() => {
    Promise.resolve().then(load)
    fetchAPI<{ token: string }>('/api/auth/media-token').then(r => setToken(r.token)).catch(() => setToken(null))
  }, [load])

  const active = job?.status === 'queued' || job?.status === 'running'
  useEffect(() => {
    if (!active) return
    const id = setInterval(load, 3000)
    return () => clearInterval(id)
  }, [active, load])

  const withToken = (path: string) => {
    if (!token) return path
    return `${path}${path.includes('?') ? '&' : '?'}token=${encodeURIComponent(token)}`
  }

  const start = async () => {
    setStarting(true)
    setError(null)
    try {
      setJob(await fetchAPI<RenderJob>(`/api/videos/${videoId}/render`, {
        method: 'POST',
        body: JSON.stringify({ subs }),
      }))
    } catch (e) {
      const text = e instanceof Error ? e.message : String(e)
      // 409 carries {detail: {problems: [...]}} — show the reasons, not the raw JSON.
      const match = text.match(/\{.*\}/s)
      try {
        const detail = match ? JSON.parse(match[0]).detail : null
        setError(Array.isArray(detail?.problems) ? detail.problems.join(' ') : typeof detail === 'string' ? detail : text)
      } catch {
        setError(text)
      }
    } finally {
      setStarting(false)
    }
  }

  const pct = job?.total_steps ? Math.round(((job.done_steps ?? 0) / job.total_steps) * 100) : 0
  const version = job?.finished_at ?? 0

  return (
    <Card className="py-4">
      <CardHeader>
        <CardTitle className="text-xs tracking-widest uppercase">{t('finalVideo.title', { title })}</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="flex flex-col gap-3">
          {job?.status === 'done' && (
            <video
              key={version}
              controls
              preload="metadata"
              src={withToken(`/api/videos/${videoId}/final.mp4?v=${version}`)}
              className="w-full rounded"
              style={{ maxHeight: 420, background: 'black' }}
            />
          )}

          <div className="flex flex-wrap items-center gap-2 text-[11px]" style={{ color: 'var(--muted)' }}>
            {job?.status === 'done' && (
              <span style={{ color: 'var(--green)' }}>
                {t('finalVideo.done', {
                  duration: job.duration ? `${Math.floor(job.duration / 60)}:${String(Math.round(job.duration % 60)).padStart(2, '0')}` : '—',
                  size: job.size_bytes ? (job.size_bytes / 1_000_000).toFixed(1) : '—',
                })}
              </span>
            )}
            {job?.status === 'none' && <span>{t('finalVideo.none')}</span>}
            {job?.status === 'failed' && <span style={{ color: 'var(--red)' }}>{t('finalVideo.failed', { error: job.error ?? '' })}</span>}
          </div>

          {active && (
            <div className="flex flex-col gap-1">
              <span className="text-[11px]" style={{ color: 'var(--text)' }}>
                {job?.status === 'queued' ? t('finalVideo.queued') : `${job?.step ?? ''} (${job?.done_steps ?? 0}/${job?.total_steps ?? 0})`}
              </span>
              <Progress value={pct} className="h-1" />
            </div>
          )}

          {job?.warnings && job.warnings.length > 0 && (
            <ul className="m-0 pl-4 list-disc text-[11px]" style={{ color: 'var(--yellow)' }}>
              {job.warnings.map(w => <li key={w}>{w}</li>)}
            </ul>
          )}
          {error && <p className="m-0 text-[11px]" style={{ color: 'var(--red)' }}>{error}</p>}

          <div className="flex flex-wrap items-center gap-2">
            <select
              value={subs}
              onChange={e => setSubs(e.target.value as SubsMode)}
              disabled={active}
              aria-label={t('finalVideo.subs')}
              className="text-[11px] px-2 py-1 rounded outline-none"
              style={{ background: 'var(--card)', color: 'var(--text)', border: '1px solid var(--border)' }}
            >
              <option value="soft">{t('finalVideo.subs.soft')}</option>
              <option value="burn">{t('finalVideo.subs.burn')}</option>
              <option value="none">{t('finalVideo.subs.none')}</option>
            </select>
            <Button size="sm" onClick={start} disabled={active || starting}>
              {job?.status === 'done' ? t('finalVideo.renderAgain') : t('finalVideo.render')}
            </Button>
            {job?.status === 'done' && (
              <>
                <Button size="sm" variant="outline" asChild>
                  <a href={withToken(`/api/videos/${videoId}/final.mp4?download=1`)}>{t('finalVideo.download')}</a>
                </Button>
                {job.captions_url && (
                  <Button size="sm" variant="outline" asChild>
                    <a href={withToken(`/api/videos/${videoId}/captions.srt?download=1`)}>{t('finalVideo.captions')}</a>
                  </Button>
                )}
              </>
            )}
            <Button size="sm" variant="ghost" asChild>
              <a href={`/review-board?video_id=${videoId}`} target="_blank" rel="noreferrer">{t('finalVideo.reviewBoard')}</a>
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>
  )
}
