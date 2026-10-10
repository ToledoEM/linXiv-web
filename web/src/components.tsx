import { colClass, type TableColumns } from './tableColumns'

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
      <col className="col-check" />
      <col />
      {cols.show.authors && <col className={colClass(cols, 'authors')} />}
      {cols.show.published && <col className="col-published" />}
      {cols.show.category && <col className={colClass(cols, 'category')} />}
      {cols.show.tags && <col className={colClass(cols, 'tags')} />}
      {cols.show.pdf && <col className="col-pdf" />}
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
