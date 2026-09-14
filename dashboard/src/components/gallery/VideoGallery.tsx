import { useState } from 'react'
import { Film } from 'lucide-react'
import { EmptyState } from '../layout/PageHeader'
import type { Orientation, Scene } from '../../types'
import { sceneMedia } from '../../lib/sceneMedia'
import VideoPlayer from './VideoPlayer'
import { Badge } from '../ui/badge'
import { useTranslation } from '../../i18n/useTranslation'

type GalleryScene = Scene & { videoTitle?: string; videoOrientation?: Orientation | null }

interface VideoGalleryProps {
  scenes: GalleryScene[]
}

export default function VideoGallery({ scenes }: VideoGalleryProps) {
  const { t } = useTranslation()
  const [activeIndex, setActiveIndex] = useState<number | null>(null)

  // Horizontal and vertical videos keep their clips in different fields.
  const videoscenes = scenes.filter(s => sceneMedia(s, s.videoOrientation).video)

  if (videoscenes.length === 0) {
    return (
      <div className="rounded-xl border border-border bg-card">
        <EmptyState icon={Film} title={t('gallery.empty')} hint={t('gallery.emptyHint')} />
      </div>
    )
  }

  return (
    <>
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
        {videoscenes.map((scene, idx) => {
          const media = sceneMedia(scene, scene.videoOrientation)
          return (
          <div
            key={scene.id}
            className="relative rounded-lg overflow-hidden cursor-pointer transition-transform hover:scale-105"
            style={{ border: '1px solid var(--border)', background: 'var(--card)' }}
            onClick={() => setActiveIndex(idx)}
          >
            {/* Thumbnail */}
            <div className="relative" style={{ aspectRatio: media.orientation === 'HORIZONTAL' ? '16/9' : '9/16' }}>
              {media.image ? (
                <img
                  src={media.image}
                  alt={t('gallery.sceneAlt', { n: scene.display_order + 1 })}
                  className="w-full h-full object-cover"
                />
              ) : (
                <div className="w-full h-full flex items-center justify-center" style={{ background: 'var(--surface)', color: 'var(--muted)' }}>
                  {t('gallery.noImage')}
                </div>
              )}

              {/* Overlay */}
              <div className="absolute inset-0 flex flex-col justify-between p-2" style={{ background: 'linear-gradient(to bottom, rgba(0,0,0,0.4) 0%, transparent 30%, transparent 70%, rgba(0,0,0,0.6) 100%)' }}>
                <div className="flex items-start justify-between gap-1">
                  <span className="text-[13px] font-bold px-1.5 py-0.5 rounded" style={{ background: 'rgba(0,0,0,0.6)', color: 'var(--text)' }}>
                    #{scene.display_order + 1}
                  </span>
                  <Badge variant={media.upscale ? 'default' : 'secondary'}>
                    {media.upscale ? t('gallery.badgeUpscaled') : t('gallery.badgeVideo')}
                  </Badge>
                </div>
                <div className="flex flex-col gap-0.5">
                  {scene.videoTitle && (
                    <span className="text-xs truncate" style={{ color: 'var(--muted)' }}>{scene.videoTitle}</span>
                  )}
                  <div className="text-[13px] truncate" style={{ color: 'var(--text)' }}>
                    {scene.prompt?.slice(0, 60) ?? ''}
                  </div>
                </div>
              </div>
            </div>
          </div>
          )
        })}
      </div>

      {activeIndex !== null && (
        <VideoPlayer
          scenes={videoscenes}
          initialIndex={activeIndex}
          onClose={() => setActiveIndex(null)}
        />
      )}
    </>
  )
}
