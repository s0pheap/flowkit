import { useCallback, useEffect, useMemo, useState } from 'react'
import { Loader2, RotateCcw, Save } from 'lucide-react'

import { fetchAPI } from '../../api/client'
import { Button } from '@/components/ui/button'
import { useTranslation } from '../../i18n/useTranslation'

export type ModelsConfig = {
  video_models: Record<string, Record<string, Record<string, string>>>
  omni_flash_models: Record<string, Record<string, string>>
  image_models: Record<string, string>
  upscale_models: Record<string, string>
  default_image_model: string
  default_video_model_family: string
  omni_flash_duration_s: number
  batch_video_models?: { accepted?: string[]; default?: string }
  // Added by GET /api/models so the UI offers exactly what PATCH accepts.
  // Optional: an agent older than that field simply omits it.
  choices?: {
    default_video_model_family?: string[]
    omni_flash_duration_s?: number[]
    default_image_model?: string[]
    batch_video_models?: string[]
  }
}

type Choices = {
  families: string[]
  durations: number[]
  imageModels: string[]
  accepted: string[]
}

/** The only list not derivable from models.json itself; used only as a fallback. */
const FALLBACK_FAMILIES = ['veo', 'omni_flash']

function withCurrent<T>(list: T[], current: T): T[] {
  return list.includes(current) ? list : [current, ...list]
}

/** What the server allows, or the best reconstruction from the payload when it
 *  predates the `choices` block. A missing list must never blank out a dropdown
 *  or drop the value the server is actually running. */
function resolveChoices(m: ModelsConfig): Choices {
  const c = m.choices ?? {}
  const durations = c.omni_flash_duration_s?.length
    ? c.omni_flash_duration_s
    : Object.keys(m.omni_flash_models?.frame_to_video ?? {})
        .map(Number)
        .filter(n => Number.isFinite(n))
        .sort((a, b) => a - b)
  const imageModels = c.default_image_model?.length
    ? c.default_image_model
    : Object.keys(m.image_models ?? {}).sort()
  return {
    families: withCurrent(
      c.default_video_model_family?.length ? c.default_video_model_family : FALLBACK_FAMILIES,
      m.default_video_model_family,
    ),
    durations: withCurrent(durations, m.omni_flash_duration_s),
    imageModels: withCurrent(imageModels, m.default_image_model),
    accepted: c.batch_video_models ?? m.batch_video_models?.accepted ?? [],
  }
}

/** models.json keys are wire names; these make the table scannable without hiding them. */
const GEN_TYPE_LABEL: Record<string, string> = {
  frame_2_video: 'Frame → video (i2v)',
  start_end_frame_2_video: 'Start + end frame',
  reference_frame_2_video: 'Reference → video (r2v)',
  frame_to_video: 'Frame → video (i2v)',
  start_end_frame_to_video: 'Start + end frame',
  reference_to_video: 'Reference → video (r2v)',
}
const ASPECT_LABEL: Record<string, string> = {
  VIDEO_ASPECT_RATIO_LANDSCAPE: 'Landscape',
  VIDEO_ASPECT_RATIO_PORTRAIT: 'Portrait',
}
const TIER_LABEL: Record<string, string> = {
  PAYGATE_TIER_ONE: 'Tier one',
  PAYGATE_TIER_TWO: 'Tier two',
}

function label(map: Record<string, string>, key: string): string {
  return map[key] ?? key
}

function Field({ name, value, onChange }: {
  name: string
  value: string
  onChange: (next: string) => void
}) {
  return (
    <label className="flex items-center gap-3 py-1">
      <span className="w-[190px] shrink-0 text-[13px] text-muted-foreground">{name}</span>
      <input
        value={value}
        onChange={e => onChange(e.target.value)}
        spellCheck={false}
        className="flex-1 min-w-0 h-8 rounded-lg border border-border bg-surface px-2.5 text-[12px] font-mono outline-none transition-colors focus:border-primary"
      />
    </label>
  )
}

function Section({ title, description, children }: {
  title: string
  description?: string
  children: React.ReactNode
}) {
  return (
    <section className="rounded-xl border border-border bg-card p-4 flex flex-col gap-2">
      <div className="flex flex-col gap-1">
        <h2 className="m-0 text-[14px] font-semibold">{title}</h2>
        {description && <p className="m-0 text-[13px] text-muted-foreground">{description}</p>}
      </div>
      <div className="flex flex-col">{children}</div>
    </section>
  )
}

export function ModelsPanel({ onError }: { onError: (e: string | null) => void }) {
  const { t } = useTranslation()
  const [server, setServer] = useState<ModelsConfig | null>(null)
  const [draft, setDraft] = useState<ModelsConfig | null>(null)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)

  const load = useCallback(async () => {
    try {
      const data = await fetchAPI<ModelsConfig>('/api/models')
      setServer(data)
      setDraft(structuredClone(data))
    } catch (e) {
      onError(e instanceof Error ? e.message : String(e))
    }
  }, [onError])

  useEffect(() => { void load() }, [load])

  const dirty = useMemo(
    () => Boolean(server && draft) && JSON.stringify(server) !== JSON.stringify(draft),
    [server, draft],
  )

  const edit = (mutate: (d: ModelsConfig) => void) => {
    setDraft(prev => {
      if (!prev) return prev
      const next = structuredClone(prev)
      mutate(next)
      return next
    })
    setSaved(false)
  }

  const save = async () => {
    if (!draft) return
    setSaving(true)
    onError(null)
    try {
      // PATCH deep-merges, so sending the full editable shape is idempotent.
      await fetchAPI('/api/models', {
        method: 'PATCH',
        body: JSON.stringify({
          default_video_model_family: draft.default_video_model_family,
          omni_flash_duration_s: draft.omni_flash_duration_s,
          default_image_model: draft.default_image_model,
          video_models: draft.video_models,
          omni_flash_models: draft.omni_flash_models,
          image_models: draft.image_models,
          upscale_models: draft.upscale_models,
        }),
      })
      await load()
      setSaved(true)
    } catch (e) {
      onError(e instanceof Error ? e.message : String(e))
    } finally {
      setSaving(false)
    }
  }

  if (!draft) {
    return <div className="flex justify-center py-10 text-faint"><Loader2 size={20} className="animate-spin" /></div>
  }

  const { families, durations, imageModels, accepted } = resolveChoices(draft)

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="m-0 text-[13px] text-muted-foreground max-w-2xl">{t('admin.models.intro')}</p>
        <div className="flex items-center gap-2">
          {saved && !dirty && <span className="text-[13px]" style={{ color: 'var(--green)' }}>{t('admin.models.saved')}</span>}
          <Button variant="outline" size="sm" disabled={!dirty || saving}
                  onClick={() => { setDraft(server ? structuredClone(server) : null); setSaved(false) }}>
            <RotateCcw size={14} />{t('admin.models.revert')}
          </Button>
          <Button disabled={!dirty || saving} onClick={save}>
            {saving ? <Loader2 size={14} className="animate-spin" /> : <Save size={14} />}
            {t('admin.models.save')}
          </Button>
        </div>
      </div>

      <Section title={t('admin.models.defaults')} description={t('admin.models.defaultsHint')}>
        <label className="flex items-center gap-3 py-1">
          <span className="w-[190px] shrink-0 text-[13px] text-muted-foreground">{t('admin.models.family')}</span>
          <select
            value={draft.default_video_model_family}
            onChange={e => edit(d => { d.default_video_model_family = e.target.value })}
            className="flex-1 min-w-0 h-8 rounded-lg border border-border bg-surface px-2 text-[13px] outline-none focus:border-primary"
          >
            {families.map(v => (
              <option key={v} value={v} style={{ background: 'var(--card)' }}>{v}</option>
            ))}
          </select>
        </label>
        <label className="flex items-center gap-3 py-1">
          <span className="w-[190px] shrink-0 text-[13px] text-muted-foreground">{t('admin.models.clipLength')}</span>
          <select
            value={String(draft.omni_flash_duration_s)}
            onChange={e => edit(d => { d.omni_flash_duration_s = Number(e.target.value) })}
            className="flex-1 min-w-0 h-8 rounded-lg border border-border bg-surface px-2 text-[13px] outline-none focus:border-primary"
          >
            {durations.map(v => (
              <option key={v} value={v} style={{ background: 'var(--card)' }}>{v}s</option>
            ))}
          </select>
        </label>
        <label className="flex items-center gap-3 py-1">
          <span className="w-[190px] shrink-0 text-[13px] text-muted-foreground">{t('admin.models.imageModel')}</span>
          <select
            value={draft.default_image_model}
            onChange={e => edit(d => { d.default_image_model = e.target.value })}
            className="flex-1 min-w-0 h-8 rounded-lg border border-border bg-surface px-2 text-[13px] outline-none focus:border-primary"
          >
            {imageModels.map(v => (
              <option key={v} value={v} style={{ background: 'var(--card)' }}>{v}</option>
            ))}
          </select>
        </label>
        <p className="m-0 mt-2 text-[12px] text-faint">{t('admin.models.projectWins')}</p>
      </Section>

      <Section title={t('admin.models.omni')} description={t('admin.models.omniHint')}>
        {Object.entries(draft.omni_flash_models ?? {}).map(([mode, durations]) => (
          <div key={mode} className="py-1.5">
            <span className="text-[13px] font-medium">{label(GEN_TYPE_LABEL, mode)}</span>
            {Object.entries(durations).map(([seconds, key]) => (
              <Field
                key={seconds}
                name={`${seconds}s`}
                value={key}
                onChange={next => edit(d => { d.omni_flash_models[mode][seconds] = next })}
              />
            ))}
          </div>
        ))}
      </Section>

      <Section title={t('admin.models.veo')} description={t('admin.models.veoHint')}>
        {accepted.length > 0 && (
          <p className="m-0 mb-2 text-[12px] text-faint">
            {t('admin.models.accepted')} <code className="font-mono">{accepted.join(', ')}</code>
          </p>
        )}
        {Object.entries(draft.video_models ?? {}).map(([tier, genTypes]) => (
          <div key={tier} className="py-1.5">
            <span className="text-[13px] font-medium">{label(TIER_LABEL, tier)}</span>
            {Object.entries(genTypes).map(([genType, aspects]) => (
              <div key={genType} className="pl-3 pt-1">
                <span className="text-[12px] text-faint">{label(GEN_TYPE_LABEL, genType)}</span>
                {Object.entries(aspects).map(([aspect, key]) => (
                  <Field
                    key={aspect}
                    name={label(ASPECT_LABEL, aspect)}
                    value={key}
                    onChange={next => edit(d => { d.video_models[tier][genType][aspect] = next })}
                  />
                ))}
              </div>
            ))}
          </div>
        ))}
      </Section>

      <Section title={t('admin.models.other')} description={t('admin.models.otherHint')}>
        {Object.entries(draft.image_models ?? {}).map(([name, key]) => (
          <Field key={name} name={name} value={key}
                 onChange={next => edit(d => { d.image_models[name] = next })} />
        ))}
        {Object.entries(draft.upscale_models ?? {}).map(([name, key]) => (
          <Field key={name} name={name} value={key}
                 onChange={next => edit(d => { d.upscale_models[name] = next })} />
        ))}
      </Section>
    </div>
  )
}
