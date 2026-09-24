import type { PropsWithChildren, ReactNode } from 'react'

interface PanelProps extends PropsWithChildren {
  title: string
  eyebrow?: string
  className?: string
  actions?: ReactNode
}

export function Panel({
  title,
  eyebrow,
  className = '',
  actions,
  children,
}: PanelProps) {
  return (
    <section className={`panel ${className}`.trim()}>
      <header className="panel__header">
        <div>
          {eyebrow && <p className="eyebrow">{eyebrow}</p>}
          <h2>{title}</h2>
        </div>
        {actions && <div className="panel__actions">{actions}</div>}
      </header>
      <div className="panel__body">{children}</div>
    </section>
  )
}
