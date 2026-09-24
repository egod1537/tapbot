type StatusTone = 'positive' | 'warning' | 'neutral' | 'danger'

interface StatusBadgeProps {
  label: string
  value: string
  tone?: StatusTone
}

export function StatusBadge({ label, value, tone = 'neutral' }: StatusBadgeProps) {
  return (
    <div className={`status-badge status-badge--${tone}`}>
      <span className="status-badge__label">{label}</span>
      <span className="status-badge__value">
        <span className="status-badge__dot" aria-hidden="true" />
        {value}
      </span>
    </div>
  )
}
