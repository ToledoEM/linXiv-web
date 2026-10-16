import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, paperPath } from '../api'
import type { Paper, SavedPdf, SavedPdfView, Stats } from '../types'
import { Authors, ErrorText } from '../components'
import { formatBytes } from '../format'
import HomeFeed from '../HomeFeed'
import { MathText } from '../tex'

// Top tags across the recent papers, as on linXiv desktop's Home.
function tagCounts(papers: Paper[]): { tag: string; count: number }[] {
  const counts = new Map<string, number>()
  for (const p of papers) for (const t of p.tags ?? []) counts.set(t, (counts.get(t) ?? 0) + 1)
  return [...counts.entries()]
    .map(([tag, count]) => ({ tag, count }))
    .sort((a, b) => b.count - a.count || a.tag.localeCompare(b.tag))
    .slice(0, 8)
}

// Home's Saved PDFs slice: which papers and how many, kept per browser.
const PDF_VIEWS: { value: SavedPdfView; label: string }[] = [
  { value: 'random', label: 'Random papers' },
  { value: 'size', label: 'Top by size' },
  { value: 'untagged', label: 'Untagged' },
]
const PDF_COUNTS = [10, 20, 30, 40, 50, 60, 70, 80, 90, 100]
const PDF_PREF = 'lxw.homePdfs'

function loadPdfPref(): { view: SavedPdfView; limit: number } {
  try {
    const raw = JSON.parse(localStorage.getItem(PDF_PREF) ?? '{}') as { view?: unknown; limit?: unknown }
    return {
      view: PDF_VIEWS.some((v) => v.value === raw.view) ? (raw.view as SavedPdfView) : 'random',
      limit: PDF_COUNTS.includes(raw.limit as number) ? (raw.limit as number) : 10,
    }
  } catch {
    return { view: 'random', limit: 10 }
  }
}

function savePdfPref(pref: { view: SavedPdfView; limit: number }) {
  try {
    localStorage.setItem(PDF_PREF, JSON.stringify(pref))
  } catch {
    // storage unavailable: the choice lasts for this page load only
  }
}

type Tile = { label: string; value: string | number; hint: string; to?: string }

export default function Home() {
  const [stats, setStats] = useState<Stats | null>(null)
  const [pdfs, setPdfs] = useState<SavedPdf[] | null>(null)
  const [pdfPref, setPdfPref] = useState(loadPdfPref)
  const [pdfError, setPdfError] = useState('')
  const [error, setError] = useState('')

  useEffect(() => {
    api
      .stats()
      .then(setStats)
      .catch((err) => setError((err as Error).message))
  }, [])

  useEffect(() => {
    api
      .pdfs(pdfPref.view, pdfPref.limit)
      .then((p) => {
        setPdfs(p.pdfs)
        setPdfError('')
      })
      .catch((err) => setPdfError((err as Error).message))
  }, [pdfPref])

  const changePdfPref = (next: { view: SavedPdfView; limit: number }) => {
    savePdfPref(next)
    setPdfPref(next)
  }

  if (error) return <ErrorText error={error} />
  if (!stats) return <p className="muted">Loading…</p>

  const coverage = stats.paper_count > 0 ? `${Math.round((stats.pdf_count / stats.paper_count) * 100)}%` : '–'
  const tiles: Tile[] = [
    { label: 'Papers', value: stats.paper_count, hint: 'in library', to: '/library' },
    { label: 'PDFs', value: stats.pdf_count, hint: 'downloaded', to: '/library' },
    { label: 'Coverage', value: coverage, hint: 'pdf per paper' },
    { label: 'Categories', value: stats.category_count, hint: 'distinct' },
    { label: 'Tags', value: stats.tag_count, hint: 'applied' },
  ]
  const recent = (stats.recent_papers ?? []).slice(0, 10)
  const topTags = tagCounts(recent)
  const maxTag = topTags[0]?.count ?? 0

  return (
    <section className="home">
      <div className="tiles">
        {tiles.map((t) => {
          const body = (
            <>
              <div className="tile-value">{t.value}</div>
              <div className="tile-label">{t.label}</div>
              <div className="tile-hint">{t.hint}</div>
            </>
          )
          return t.to ? (
            <Link key={t.label} to={t.to} className="tile tile-link">
              {body}
            </Link>
          ) : (
            <div key={t.label} className="tile">
              {body}
            </div>
          )
        })}
      </div>

      <HomeFeed />

      <div className="home-panels">
        <div>
          <h3>Recent papers</h3>
          {recent.length === 0 ? (
            <p className="card muted center">No papers yet. Add some from the Search or Add Paper pages.</p>
          ) : (
            <ul className="results">
              {recent.map((p) => (
                <li key={p.source_id} className="card">
                  <div className="result-head">
                    <Link to={paperPath(p.source_id)}>
                      <MathText forceInline>{p.title}</MathText>
                    </Link>
                    {p.has_pdf && <span className="pill">PDF</span>}
                  </div>
                  <Authors authors={p.authors} max={4} />
                  <div className="muted small">
                    {p.published} {p.category && <span className="pill">{p.category}</span>}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div>
          <h3>Tags: recent papers</h3>
          {topTags.length === 0 ? (
            <p className="card muted center">No tags on recent papers yet.</p>
          ) : (
            <ul className="card tag-bars">
              {topTags.map(({ tag, count }) => (
                <li key={tag}>
                  <Link to={`/library?tag=${encodeURIComponent(tag)}`} className="tag-bar">
                    <span className="tag-bar-head">
                      <span>{tag}</span>
                      <span className="muted">{count}</span>
                    </span>
                    <span className="tag-bar-track">
                      <span className="tag-bar-fill" style={{ width: `${(count / maxTag) * 100}%` }} />
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>

      <div className="section-head">
        <h3>Saved PDFs</h3>
        <div className="toolbar">
          <select
            aria-label="Which saved PDFs"
            value={pdfPref.view}
            onChange={(e) => changePdfPref({ ...pdfPref, view: e.target.value as SavedPdfView })}
          >
            {PDF_VIEWS.map((v) => (
              <option key={v.value} value={v.value}>
                {v.label}
              </option>
            ))}
          </select>
          <select
            aria-label="How many"
            value={pdfPref.limit}
            onChange={(e) => changePdfPref({ ...pdfPref, limit: Number(e.target.value) })}
          >
            {PDF_COUNTS.map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </select>
        </div>
      </div>
      <ErrorText error={pdfError} />
      {pdfs === null ? (
        <p className="muted">Loading…</p>
      ) : pdfs.length === 0 ? (
        <p className="muted">{pdfPref.view === 'untagged' ? 'No untagged papers with a PDF.' : 'None yet.'}</p>
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
                    <Link to={paperPath(p.source_id)}>
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
