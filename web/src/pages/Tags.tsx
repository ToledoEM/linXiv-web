import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'
import { ErrorText } from '../components'
import type { TagCounts } from '../types'

type SortKey = 'tag' | 'count'
type Sort = { key: SortKey; dir: 'asc' | 'desc' }

export default function Tags() {
  const [data, setData] = useState<TagCounts | null>(null)
  const [error, setError] = useState('')
  const [q, setQ] = useState('')
  const [sort, setSort] = useState<Sort>({ key: 'count', dir: 'desc' })

  useEffect(() => {
    api
      .tagCounts()
      .then((d) => {
        setData(d)
        setError('')
      })
      .catch((err) => setError((err as Error).message))
  }, [])

  const shown = useMemo(() => {
    const needle = q.trim().toLowerCase()
    const dir = sort.dir === 'asc' ? 1 : -1
    return (data?.tags ?? [])
      .filter((t) => !needle || t.tag.toLowerCase().includes(needle))
      .sort((a, b) => {
        const primary = sort.key === 'tag' ? a.tag.localeCompare(b.tag) : a.count - b.count
        return primary !== 0 ? primary * dir : a.tag.localeCompare(b.tag)
      })
  }, [data, q, sort])

  // Clicking the active column flips direction; a new column starts at its natural order.
  const sortBy = (key: SortKey) =>
    setSort((s) =>
      s.key === key ? { key, dir: s.dir === 'asc' ? 'desc' : 'asc' } : { key, dir: key === 'tag' ? 'asc' : 'desc' },
    )
  const arrow = (key: SortKey) => (sort.key === key ? (sort.dir === 'asc' ? ' ▲' : ' ▼') : '')

  if (!data) return error ? <ErrorText error={error} /> : <p className="muted">Loading…</p>

  return (
    <section>
      <h2>Tags</h2>
      <p className="muted small library-count">
        {data.tags.length} tag{data.tags.length === 1 ? '' : 's'} · {data.total} paper{data.total === 1 ? '' : 's'} ·{' '}
        {data.untagged} untagged
      </p>
      <div className="toolbar">
        <input
          className="grow"
          type="search"
          aria-label="Filter tags"
          placeholder="Filter tags…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
      </div>
      <ErrorText error={error} />
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>
                <button className="link th-sort" onClick={() => sortBy('tag')}>
                  Tag{arrow('tag')}
                </button>
              </th>
              <th className="num">
                <button className="link th-sort" onClick={() => sortBy('count')}>
                  Papers{arrow('count')}
                </button>
              </th>
            </tr>
          </thead>
          <tbody>
            {!q.trim() && (
              <tr>
                <td>
                  <Link to="/library?untagged=1">
                    <em>Untagged</em>
                  </Link>
                </td>
                <td className="num">{data.untagged}</td>
              </tr>
            )}
            {shown.map((t) => (
              <tr key={t.tag}>
                <td>
                  <Link to={`/library?tag=${encodeURIComponent(t.tag)}`}>{t.tag}</Link>
                </td>
                <td className="num">{t.count}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {shown.length === 0 && q.trim() && <p className="muted">No tags match your filter.</p>}
      {data.tags.length === 0 && <p className="muted">No tags yet.</p>}
    </section>
  )
}
