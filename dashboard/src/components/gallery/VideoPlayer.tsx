import { useState, useEffect } from 'react'
import type { Orientation, Scene } from '../../types'
import { sceneMedia } from '../../lib/sceneMedia'
import { useTranslation } from '../../i18n/useTranslation'
import { chainLabel } from '../../i18n/labels'

type GalleryScene = Scene & { videoTitle?: string; videoOrientation?: Orientation | null }

interface VideoPlayerProps {
  scenes: GalleryScene[]
  initialIndex: number
  onClose: () => void
}

function parseCharacterNames(raw: string | null): string[] {
  if (!raw) return []
  try {
    const parsed = JSON.parse(raw)
    if (Array.isArray(parsed)) return parsed
    return []
  } catch {
    return []
  }
}

export default function VideoPlayer({ scenes, initialIndex, onClose }: VideoPlayerProps) {
  const { t } = useTranslation()
  const [index, setIndex] = useState(initialIndex)
  const scene = scenes[index]

  const media = sceneMedia(scene, scene.videoOrientation)
  const videoSrc = media.upscale || media.video || ''
  const charNames = parseCharacterNames(scene.character_names)

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') onClose()
      if (e.key === 'ArrowLeft' && index > 0) setIndex(i => i - 1)
      if (e.key === 'ArrowRight' && index < scenes.length - 1) setIndex(i => i + 1)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [index, scenes.length, onClose])

  function chainBadgeStyle(ct: string) {
    if (ct === 'ROOT') return { background: 'var(--accent)', color: '#fff' }
    if (ct === 'CONTINUATION') return { background: 'var(--green)', color: '#fff' }
    return { background: 'var(--yellow)', color: '#000' }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center"
      style={{ background: 'rgba(0,0,0,0.85)' }}
      onClick={onClose}
    >
      <div
        className="flex rounded-lg overflow-hidden relative"
        style={{ maxHeight: '90vh', maxWidth: '90vw', background: 'var(--surface)' }}
        onClick={e => e.stopPropagation()}
      >
        {/* Close button */}
        <button
          className="absolute top-2 right-2 z-10 w-7 h-7 rounded-full flex items-center justify-center text-[13px] font-bold"
          style={{ background: 'rgba(0,0,0,0.6)', color: 'var(--text)' }}
          onClick={onClose}
        >
          X
        </button>

        {/* Video */}
        <div className="flex items-center justify-center" style={{ background: '#000', minWidth: 280, maxWidth: '60vw' }}>
          <video
            key={videoSrc}
            src={videoSrc}
            controls
            autoPlay
            className="h-full"
            style={{ maxHeight: '90vh', maxWidth: '60vw', display: 'block' }}
          />
        </div>

        {/* Sidebar */}
        <div
          className="flex flex-col p-4 gap-3 overflow-y-auto"
          style={{ width: 320, background: 'var(--surface)', borderLeft: '1px solid var(--border)' }}
        >
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-[13px] font-bold px-2 py-0.5 rounded" style={{ background: 'var(--card)', color: 'var(--muted)' }}>
              {scene.videoTitle ? `${scene.videoTitle} · ` : ''}{t('videoPlayer.sceneLabel', { n: scene.display_order + 1 })}
            </span>
            <span className="text-[13px] font-semibold px-2 py-0.5 rounded" style={chainBadgeStyle(scene.chain_type)}>
              {chainLabel(t, scene.chain_type)}
            </span>
          </div>

          {scene.prompt && (
            <div>
              <div className="text-[13px] font-bold mb-1" style={{ color: 'var(--muted)' }}>{t('videoPlayer.prompt')}</div>
              <div className="text-[13px]" style={{ color: 'var(--text)' }}>{scene.prompt}</div>
            </div>
          )}

          {scene.video_prompt && (
            <div>
              <div className="text-[13px] font-bold mb-1" style={{ color: 'var(--muted)' }}>{t('videoPlayer.videoPrompt')}</div>
              <div className="text-[13px] whitespace-pre-wrap" style={{ color: 'var(--text)' }}>{scene.video_prompt}</div>
            </div>
          )}

          {charNames.length > 0 && (
            <div>
              <div className="text-[13px] font-bold mb-1" style={{ color: 'var(--muted)' }}>{t('videoPlayer.characters')}</div>
              <div className="flex flex-wrap gap-1">
                {charNames.map(name => (
                  <span key={name} className="text-[13px] px-2 py-0.5 rounded" style={{ background: 'var(--card)', color: 'var(--accent)' }}>
                    {name}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Download */}
          <a
            href={videoSrc}
            download={`scene-${scene.display_order + 1}.mp4`}
            className="text-[13px] px-3 py-1.5 rounded text-center font-semibold mt-auto"
            style={{ background: 'var(--accent)', color: '#fff', textDecoration: 'none' }}
          >
            {t('videoPlayer.download')}
          </a>

          {/* Prev / Next */}
          <div className="flex gap-2">
            <button
              disabled={index === 0}
              onClick={() => setIndex(i => i - 1)}
              className="fk-input flex-1 text-[13px]  font-semibold disabled:opacity-30"
            >
              {t('videoPlayer.prev')}
            </button>
            <button
              disabled={index === scenes.length - 1}
              onClick={() => setIndex(i => i + 1)}
              className="fk-input flex-1 text-[13px]  font-semibold disabled:opacity-30"
            >
              {t('videoPlayer.next')}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
