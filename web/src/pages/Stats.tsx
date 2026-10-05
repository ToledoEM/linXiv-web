import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, idPath } from '../api'
import type { SavedPdf, Stats } from '../types'
import { ErrorText } from '../components'
import { formatBytes } from '../format'
import { MathText } from '../tex'

export default function StatsPage() {
  const [stats, setStats] = useState<Stats | null>(null)
  const [pdfs, setPdfs] = useState<SavedPdf[]>([])
  const [storage, setStorage] = useState<{ storage_mb: number } | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    Promise.all([api.stats(), api.pdfs(), api.storage()])
      .then(([s, p, st]) => {
        setStats(s)
        setPdfs(p.pdfs)
        setStorage(st)
      })
      .catch((err) => setError((err as Error).message))
  }, [])

  if (error) return <ErrorText error={error} />
  if (!stats) return <p className="muted">Loading…</p>

  const tiles: [string, string | number][] = [
    ['Papers', stats.paper_count],
    ['PDFs', stats.pdf_count],
    ['Tags', stats.tag_count],
    ['Categories', stats.category_count],
    ['PDF storage', storage ? `${storage.storage_mb.toFixed(1)} MB` : '—'],
  ]

  return (
    <section>
      <h2>Stats</h2>
      <div className="tiles">
        {tiles.map(([label, value]) => (
          <div key={label} className="tile">
            <div className="tile-value">{value}</div>
            <div className="muted small">{label}</div>
          </div>
        ))}
      </div>

      <h3>Recently added</h3>
      <ul className="plain">
        {stats.recent_papers?.map((p) => (
          <li key={p.source_id}>
            <Link to={`/paper/${idPath(p.source_id)}`}>
              <MathText forceInline>{p.title}</MathText>
            </Link>{' '}
            <span className="muted small">{p.published}</span>
          </li>
        ))}
      </ul>

      <h3>Saved PDFs</h3>
      {pdfs.length === 0 ? (
        <p className="muted">None yet.</p>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Paper</th>
                <th>Version</th>
                <th>Size</th>
              </tr>
            </thead>
            <tbody>
              {pdfs.map((p) => (
                <tr key={p.source_id}>
                  <td>
                    <Link to={`/paper/${idPath(p.source_id)}`}>
                      <MathText forceInline>{p.title}</MathText>
                    </Link>
                  </td>
                  <td>v{p.version}</td>
                  <td className="nowrap">{formatBytes(p.size_bytes)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}
