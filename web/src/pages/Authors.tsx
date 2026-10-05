import { useEffect, useMemo, useState } from 'react'
import { api } from '../api'
import { nameSortKey, type NameSortBy } from '../authorName'
import { ErrorText } from '../components'
import type { Author } from '../types'

type SortKey = 'name' | 'paper_count'
type Sort = { key: SortKey; dir: 'asc' | 'desc' }

const HIDE_KEY = 'lxw.authors.hideSingle'

function loadHide(): boolean {
  try {
    return localStorage.getItem(HIDE_KEY) === '1'
  } catch {
    return false
  }
}

// Full, first or last name, and ORCID.
function matches(a: Author, q: string): boolean {
  if (!q) return true
  return [a.full_name, a.first_name, a.last_name, a.orcid].some((f) => f?.toLowerCase().includes(q))
}

export default function Authors() {
  const [authors, setAuthors] = useState<Author[] | null>(null)
  const [error, setError] = useState('')
  const [q, setQ] = useState('')
  const [hideSingle, setHideSingle] = useState(loadHide)
  const [nameBy, setNameBy] = useState<NameSortBy>('full_name')
  const [sort, setSort] = useState<Sort>({ key: 'name', dir: 'asc' })

  useEffect(() => {
    try {
      localStorage.setItem(HIDE_KEY, hideSingle ? '1' : '0')
    } catch {
      // storage unavailable: preference lasts for this page load only
    }
    api
      .authors(hideSingle)
      .then((a) => {
        setAuthors(a)
        setError('')
      })
      .catch((err) => setError((err as Error).message))
  }, [hideSingle])

  const shown = useMemo(() => {
    const needle = q.trim().toLowerCase()
    const dir = sort.dir === 'asc' ? 1 : -1
    return (authors ?? [])
      .filter((a) => matches(a, needle))
      .map((author) => ({ author, key: nameSortKey(author, nameBy) }))
      .sort((a, b) => {
        const primary =
          sort.key === 'name' ? a.key.localeCompare(b.key) : a.author.paper_count - b.author.paper_count
        return primary !== 0 ? primary * dir : a.key.localeCompare(b.key)
      })
      .map((k) => k.author)
  }, [authors, q, nameBy, sort])

  // Clicking the active column flips direction; a new column starts at its natural order.
  const sortBy = (key: SortKey) =>
    setSort((s) =>
      s.key === key ? { key, dir: s.dir === 'asc' ? 'desc' : 'asc' } : { key, dir: key === 'name' ? 'asc' : 'desc' },
    )
  const arrow = (key: SortKey) => (sort.key === key ? (sort.dir === 'asc' ? ' ▲' : ' ▼') : '')

  if (!authors) return error ? <ErrorText error={error} /> : <p className="muted">Loading…</p>

  return (
    <section>
      <h2>Authors</h2>
      <p className="muted small library-count">
        {authors.length} author{authors.length === 1 ? '' : 's'}
        {hideSingle ? ' with multiple papers' : ' in your library'}
      </p>
      <div className="toolbar">
        <input className="grow" placeholder="Filter by name or ORCID…" value={q} onChange={(e) => setQ(e.target.value)} />
        <label className="check">
          <input type="checkbox" checked={hideSingle} onChange={(e) => setHideSingle(e.target.checked)} />
          Hide single-paper authors
        </label>
        <label className="check">
          Sort names by
          <select
            value={nameBy}
            onChange={(e) => {
              setNameBy(e.target.value as NameSortBy)
              setSort((s) => (s.key === 'name' ? s : { key: 'name', dir: 'asc' }))
            }}
          >
            <option value="full_name">Full name</option>
            <option value="first_name">First name</option>
            <option value="last_name">Last name</option>
          </select>
        </label>
      </div>
      <ErrorText error={error} />
      {shown.length === 0 ? (
        <p className="muted">
          {q.trim() ? 'No authors match your filter.' : hideSingle ? 'No authors with more than one paper.' : 'No authors yet.'}
        </p>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>
                  <button className="link th-sort" onClick={() => sortBy('name')}>
                    Author{arrow('name')}
                  </button>
                </th>
                <th>ORCID</th>
                <th className="num">
                  <button className="link th-sort" onClick={() => sortBy('paper_count')}>
                    Papers{arrow('paper_count')}
                  </button>
                </th>
              </tr>
            </thead>
            <tbody>
              {shown.map((a) => (
                <tr key={a.author_id}>
                  <td>{a.full_name ?? '(unnamed)'}</td>
                  <td className="mono">
                    {a.orcid && (
                      <a href={`https://orcid.org/${encodeURIComponent(a.orcid)}`} target="_blank" rel="noreferrer">
                        {a.orcid}
                      </a>
                    )}
                  </td>
                  <td className="num">{a.paper_count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}
