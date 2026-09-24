interface JsonSyntaxHighlightProps {
  value: unknown
}

const JSON_TOKEN =
  /"(?:\\.|[^"\\])*"(?=\s*:)|"(?:\\.|[^"\\])*"|-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?|\b(?:true|false|null)\b/g

function rawText(value: unknown): string {
  if (typeof value === 'string') {
    try {
      return JSON.stringify(JSON.parse(value) as unknown, null, 2)
    } catch {
      return value
    }
  }
  return JSON.stringify(value, null, 2) ?? String(value)
}

function tokenClass(token: string, source: string, end: number): string {
  if (token.startsWith('"')) {
    return /^\s*:/.test(source.slice(end)) ? 'json-key' : 'json-string'
  }
  if (token === 'true' || token === 'false') return 'json-boolean'
  if (token === 'null') return 'json-null'
  return 'json-number'
}

export function JsonSyntaxHighlight({ value }: JsonSyntaxHighlightProps) {
  const source = rawText(value)
  const content: React.ReactNode[] = []
  let cursor = 0

  for (const match of source.matchAll(JSON_TOKEN)) {
    const index = match.index
    const token = match[0]
    if (index > cursor) content.push(source.slice(cursor, index))
    const end = index + token.length
    content.push(
      <span
        className={tokenClass(token, source, end)}
        key={`${index.toString()}-${token}`}
      >
        {token}
      </span>,
    )
    cursor = end
  }
  if (cursor < source.length) content.push(source.slice(cursor))

  return (
    <pre className="json-view">
      <code>{content}</code>
    </pre>
  )
}
