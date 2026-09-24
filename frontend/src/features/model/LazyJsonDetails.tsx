import { useState } from 'react'
import { JsonSyntaxHighlight } from './JsonSyntaxHighlight'

interface LazyJsonDetailsProps {
  value: unknown
  title: string
  hint: string
  className?: string
}

export function LazyJsonDetails({
  value,
  title,
  hint,
  className = '',
}: LazyJsonDetailsProps) {
  const [isOpen, setOpen] = useState(false)

  return (
    <details
      className={className}
      onToggle={(event) => setOpen(event.currentTarget.open)}
    >
      <summary>
        <span>{title}</span>
        <small>{hint}</small>
      </summary>
      {isOpen && <JsonSyntaxHighlight value={value} />}
    </details>
  )
}
