import type { ReactNode } from 'react'

interface KeyValueRowProps {
  label: string
  value: ReactNode
  accent?: boolean
}

export function KeyValueRow({ label, value, accent = false }: KeyValueRowProps) {
  return (
    <div className="key-value-row">
      <dt>{label}</dt>
      <dd className={accent ? 'is-accent' : undefined}>{value}</dd>
    </div>
  )
}
