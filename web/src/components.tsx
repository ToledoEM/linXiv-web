export function Authors({ authors, max = 6 }: { authors: string[]; max?: number }) {
  if (!authors?.length) return null
  const shown = authors.slice(0, max).join(', ')
  return (
    <div className="authors">
      {shown}
      {authors.length > max && ` +${authors.length - max} more`}
    </div>
  )
}

/** Table header that sorts on click, ▲/▼ on the active column. */
export function SortHeader({
  label,
  dir,
  onClick,
}: {
  label: string
  dir: 'asc' | 'desc' | null
  onClick: () => void
}) {
  return (
    <th className="nowrap" aria-sort={dir === 'asc' ? 'ascending' : dir === 'desc' ? 'descending' : undefined}>
      <button className="link th-sort" onClick={onClick}>
        {label}
        {dir === 'asc' ? ' ▲' : dir === 'desc' ? ' ▼' : ''}
      </button>
    </th>
  )
}

export function ErrorText({ error }: { error?: string }) {
  return error ? <p className="error">{error}</p> : null
}
