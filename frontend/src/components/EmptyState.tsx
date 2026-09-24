import type { ReactNode } from 'react'

interface EmptyStateProps {
  icon?: ReactNode
  title: string
  description: string
  compact?: boolean
}

export function EmptyState({
  icon,
  title,
  description,
  compact = false,
}: EmptyStateProps) {
  return (
    <div className={compact ? 'empty-state is-compact' : 'empty-state'}>
      {icon && <span className="empty-state__icon">{icon}</span>}
      <strong>{title}</strong>
      <p>{description}</p>
    </div>
  )
}
