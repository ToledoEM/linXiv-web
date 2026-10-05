import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, idPath } from '../api'
import type { Paper } from '../types'
import { ErrorText } from '../components'
import { MathText } from '../tex'

export default function Library() {
  const [q, setQ] = useState('')
  const [tag, setTag] = useState('')
  const [fulltext, setFulltext] = useState(false)
  const [sort, setSort] = useState('published')
  const [tags, setTags] = useState<string[]>([])
  const [papers, setPapers] = useState<Paper[] | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    api.allTags().then(setTags).catch(() => setTags([]))
  }, [])

  useEffect(() => {
    let cancelled = false
    const t = setTimeout(() => {
      api
        .papers({ q: q.trim() || undefined, tag: tag || undefined, fulltext: fulltext || undefined, sort, limit: 500 })
        .then((p) => {
          if (!cancelled) {
            setPapers(p)
            setError('')
          }
        })
        .catch((err) => !cancelled && setError((err as Error).message))
    }, 250)
    return () => {
      cancelled = true
      clearTimeout(t)
    }
  }, [q, tag, fulltext, sort])

  return (
    <section>
      <h2>Library</h2>
      <div className="toolbar">
        <input
          className="grow"
          placeholder={fulltext ? 'Full-text search (indexed TeX sources)' : 'Filter by title, author, id, tag…'}
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
        <label className="check">
          <input type="checkbox" checked={fulltext} onChange={(e) => setFulltext(e.target.checked)} />
          Full text
        </label>
        <select value={tag} onChange={(e) => setTag(e.target.value)} disabled={fulltext}>
          <option value="">All tags</option>
          {tags.map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </select>
        <select value={sort} onChange={(e) => setSort(e.target.value)} disabled={fulltext}>
          <option value="published">Newest published</option>
          <option value="added">Recently added</option>
          <option value="title">Title</option>
        </select>
      </div>
      <ErrorText error={error} />
      {papers && papers.length === 0 && <p className="muted">No papers.</p>}
      {papers && papers.length > 0 && (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Title</th>
                <th>Authors</th>
                <th>Published</th>
                <th>Category</th>
                <th>Tags</th>
                <th>PDF</th>
              </tr>
            </thead>
            <tbody>
              {papers.map((p) => (
                <tr key={p.source_id}>
                  <td>
                    <Link to={`/paper/${idPath(p.source_id)}`}>
                      <MathText forceInline>{p.title}</MathText>
                    </Link>
                  </td>
                  <td className="small">
                    {p.authors?.slice(0, 3).join(', ')}
                    {p.authors?.length > 3 && ' et al.'}
                  </td>
                  <td className="nowrap">{p.published}</td>
                  <td>{p.category}</td>
                  <td>
                    {p.tags?.map((t) => (
                      <span key={t} className="pill">
                        {t}
                      </span>
                    ))}
                  </td>
                  <td>{p.has_pdf ? '✓' : ''}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}
