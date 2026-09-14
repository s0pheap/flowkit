import type { ReactNode } from 'react'
import type { LucideIcon } from 'lucide-react'

/** Title block at the top of a page, with optional actions on the right. */
export function PageHeader({ title, description, actions, children }: {
  title: ReactNode
  description?: ReactNode
  actions?: ReactNode
  children?: ReactNode
}) {
  return (
    <div className="flex flex-col gap-4 mb-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div className="flex flex-col gap-1.5 min-w-0">
          <h1 className="m-0 text-[26px] leading-tight font-semibold tracking-[-0.02em] text-foreground">{title}</h1>
          {description && <p className="m-0 text-[14px] leading-relaxed text-muted-foreground max-w-3xl">{description}</p>}
        </div>
        {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
      </div>
      {children}
    </div>
  )
}

/** Centered placeholder for an empty list or panel. */
export function EmptyState({ icon: Icon, title, hint, compact = false }: {
  icon: LucideIcon
  title: ReactNode
  hint?: ReactNode
  compact?: boolean
}) {
  return (
    <div className={`flex flex-col items-center justify-center text-center gap-3 ${compact ? 'py-8' : 'py-16'}`}>
      <span className="w-11 h-11 rounded-xl flex items-center justify-center border border-border bg-surface text-faint">
        <Icon size={20} strokeWidth={1.8} />
      </span>
      <div className="flex flex-col gap-1">
        <span className="text-[14px] font-medium text-foreground">{title}</span>
        {hint && <span className="text-[13px] text-muted-foreground max-w-sm">{hint}</span>}
      </div>
    </div>
  )
}
