import { useCallback, useEffect, useRef, useState } from 'react'
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
  music?: { track: string; volume: number } | null
}

interface MusicTrack {
  name: string
  size_bytes: number
  duration: number | null
  url: string
}

type SubsMode = 'soft' | 'burn' | 'none'

const clock = (seconds: number) => `${Math.floor(seconds / 60)}:${String(Math.round(seconds % 60)).padStart(2, '0')}`

/** The server-side final cut for one video: start a render, follow it, watch and download the result. */
export default function FinalVideoPanel({ videoId, title }: { videoId: string; title: string }) {
  const { t } = useTranslation()
  const [job, setJob] = useState<RenderJob | null>(null)
  const [token, setToken] = useState<string | null>(null)
  const [subs, setSubs] = useState<SubsMode>('soft')
  const [error, setError] = useState<string | null>(null)
  const [starting, setStarting] = useState(false)
  const [tracks, setTracks] = useState<MusicTrack[]>([])
  const [track, setTrack] = useState('')
  const [volume, setVolume] = useState(0.15)
  const [uploading, setUploading] = useState(false)
  const fileInput = useRef<HTMLInputElement>(null)

  const loadTracks = useCallback(async () => {
    try {
      const list = (await fetchAPI<{ tracks: MusicTrack[] }>(`/api/videos/${videoId}/music`)).tracks
      setTracks(list)
      setTrack(current => (list.some(m => m.name === current) ? current : ''))
    } catch {
      setTracks([])
    }
  }, [videoId])

  const load = useCallback(async () => {
    try {
      setJob(await fetchAPI<RenderJob>(`/api/videos/${videoId}/render`))
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }, [videoId])

  useEffect(() => {
    Promise.resolve().then(load)
    Promise.resolve().then(loadTracks)
    fetchAPI<{ token: string }>('/api/auth/media-token').then(r => setToken(r.token)).catch(() => setToken(null))
  }, [load, loadTracks])

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
        body: JSON.stringify({ subs, music: track ? { track, volume } : undefined }),
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

  const upload = async (file: File) => {
    setUploading(true)
    setError(null)
    try {
      const saved = await fetchAPI<MusicTrack>(`/api/videos/${videoId}/music/${encodeURIComponent(file.name)}`, {
        method: 'PUT',
        body: file,
        headers: { 'Content-Type': file.type || 'application/octet-stream' },
      })
      await loadTracks()
      setTrack(saved.name)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setUploading(false)
      if (fileInput.current) fileInput.current.value = ''
    }
  }

  const selected = tracks.find(m => m.name === track)
  const pct = job?.total_steps ? Math.round(((job.done_steps ?? 0) / job.total_steps) * 100) : 0
  const version = job?.finished_at ?? 0

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-[15px]">{t('finalVideo.title', { title })}</CardTitle>
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

          <div className="flex flex-wrap items-center gap-2 text-[13px]" style={{ color: 'var(--muted)' }}>
            {job?.status === 'done' && (
              <span style={{ color: 'var(--green)' }}>
                {t('finalVideo.done', {
                  duration: job.duration ? clock(job.duration) : '—',
                  size: job.size_bytes ? (job.size_bytes / 1_000_000).toFixed(1) : '—',
                })}
              </span>
            )}
            {job?.status === 'done' && job.music && <span>{t('finalVideo.music.used', { track: job.music.track })}</span>}
            {job?.status === 'none' && <span>{t('finalVideo.none')}</span>}
            {job?.status === 'failed' && <span style={{ color: 'var(--red)' }}>{t('finalVideo.failed', { error: job.error ?? '' })}</span>}
          </div>

          {active && (
            <div className="flex flex-col gap-1">
              <span className="text-[13px]" style={{ color: 'var(--text)' }}>
                {job?.status === 'queued' ? t('finalVideo.queued') : `${job?.step ?? ''} (${job?.done_steps ?? 0}/${job?.total_steps ?? 0})`}
              </span>
              <Progress value={pct} className="h-1" />
            </div>
          )}

          {job?.warnings && job.warnings.length > 0 && (
            <ul className="m-0 pl-4 list-disc text-[13px]" style={{ color: 'var(--yellow)' }}>
              {job.warnings.map(w => <li key={w}>{w}</li>)}
            </ul>
          )}
          {error && <p className="m-0 text-[13px]" style={{ color: 'var(--red)' }}>{error}</p>}

          <div className="flex flex-col gap-2">
            <div className="flex flex-wrap items-center gap-2 text-[13px]">
              <select
                value={track}
                onChange={e => setTrack(e.target.value)}
                disabled={active}
                aria-label={t('finalVideo.music')}
                className="fk-input text-[13px] outline-none"
                style={{ maxWidth: '100%' }}
              >
                <option value="">{t('finalVideo.music.none')}</option>
                {tracks.map(m => (
                  <option key={m.name} value={m.name}>{m.duration ? `${m.name} (${clock(m.duration)})` : m.name}</option>
                ))}
              </select>
              {track && (
                <label className="flex items-center gap-2" style={{ color: 'var(--muted)' }}>
                  {t('finalVideo.music.volume')}
                  <input
                    type="range"
                    min={0.05}
                    max={0.5}
                    step={0.05}
                    value={volume}
                    disabled={active}
                    onChange={e => setVolume(Number(e.target.value))}
                  />
                  <span style={{ minWidth: '4ch' }}>{Math.round(volume * 100)}%</span>
                </label>
              )}
              <input
                ref={fileInput}
                type="file"
                accept=".mp3,.wav,.m4a,.aac,.ogg,.flac,audio/*"
                hidden
                onChange={e => { const file = e.target.files?.[0]; if (file) upload(file) }}
              />
              <Button size="sm" variant="outline" onClick={() => fileInput.current?.click()} disabled={active || uploading}>
                {uploading ? t('finalVideo.music.uploading') : t('finalVideo.music.upload')}
              </Button>
            </div>
            {selected && (
              <audio key={selected.name} controls preload="none" src={withToken(selected.url)} className="w-full" style={{ height: 32 }} />
            )}
            <span className="text-[12px]" style={{ color: 'var(--muted)' }}>{t('finalVideo.music.hint')}</span>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <select
              value={subs}
              onChange={e => setSubs(e.target.value as SubsMode)}
              disabled={active}
              aria-label={t('finalVideo.subs')}
              className="fk-input text-[13px]   outline-none"
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
