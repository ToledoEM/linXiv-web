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

export function ErrorText({ error }: { error?: string }) {
  return error ? <p className="error">{error}</p> : null
}
