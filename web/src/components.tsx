import { colRem, FIXED_REM, type TableColumns } from './tableColumns'

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

/** `<colgroup>` for the paper tables: check box, title (takes the rest), then the shown optional columns. */
export function PaperColGroup({ cols }: { cols: TableColumns }) {
  return (
    <colgroup>
      <col style={{ width: `${FIXED_REM.check}rem` }} />
      <col />
      {cols.show.authors && <col style={{ width: `${colRem(cols, 'authors')}rem` }} />}
      {cols.show.published && <col style={{ width: `${FIXED_REM.published}rem` }} />}
      {cols.show.category && <col style={{ width: `${colRem(cols, 'category')}rem` }} />}
      {cols.show.tags && <col style={{ width: `${colRem(cols, 'tags')}rem` }} />}
      {cols.show.pdf && <col style={{ width: `${FIXED_REM.pdf}rem` }} />}
    </colgroup>
  )
}

/** DOI line under a paper title, linked to doi.org. */
export function DoiLine({ doi }: { doi?: string | null }) {
  if (!doi?.trim()) return null
  return (
    <a className="muted small mono block doi-line" href={`https://doi.org/${doi.trim()}`} target="_blank" rel="noreferrer">
      {doi.trim()}
    </a>
  )
}

/** Tag pills that wrap whole, never cut mid-word. */
export function TagCell({ tags }: { tags?: string[] }) {
  return (
    <td>
      <div className="tags-cell">
        {tags?.map((t) => (
          <span key={t} className="pill" title={t}>
            {t}
          </span>
        ))}
      </div>
    </td>
  )
}
