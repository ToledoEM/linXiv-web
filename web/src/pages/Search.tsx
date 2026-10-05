import { useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { api, idPath } from '../api'
import type { Paper, SearchResult, Source } from '../types'
import { Authors, ErrorText } from '../components'

type RowState = { busy?: boolean; paper?: Paper; error?: string }

export default function Search() {
  const [q, setQ] = useState('')
  const [source, setSource] = useState<Source>('arxiv')
  const [max, setMax] = useState(10)
  const [results, setResults] = useState<SearchResult[] | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [rows, setRows] = useState<Record<string, RowState>>({})

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    if (!q.trim()) return
    setBusy(true)
    setError('')
    setRows({})
    try {
      setResults(await api.search(q.trim(), source, max))
    } catch (err) {
      setError(String((err as Error).message))
      setResults(null)
    } finally {
      setBusy(false)
    }
  }

  const add = async (r: SearchResult, withPdf: boolean) => {
    const set = (s: RowState) => setRows((prev) => ({ ...prev, [r.source_id]: s }))
    set({ busy: true })
    try {
      const paper = await api.fetch(r.source_id, source)
      if (withPdf) await api.downloadPdf(paper.source_id)
      set({ paper })
    } catch (err) {
      set({ error: (err as Error).message })
    }
  }

  return (
    <section>
      <h2>Search</h2>
      <form className="toolbar" onSubmit={submit}>
        <input
          className="grow"
          placeholder="Title, author, keywords…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          autoFocus
        />
        <select value={source} onChange={(e) => setSource(e.target.value as Source)}>
          <option value="arxiv">arXiv</option>
          <option value="openalex">OpenAlex</option>
          <option value="crossref">Crossref</option>
        </select>
        <select value={max} onChange={(e) => setMax(Number(e.target.value))}>
          {[10, 25, 50].map((n) => (
            <option key={n} value={n}>
              {n} results
            </option>
          ))}
        </select>
        <button disabled={busy}>{busy ? 'Searching…' : 'Search'}</button>
      </form>
      <ErrorText error={error} />
      {results && results.length === 0 && <p className="muted">No results.</p>}
      <ul className="results">
        {results?.map((r) => {
          const row = rows[r.source_id] ?? {}
          return (
            <li key={r.entry_id ?? r.source_id} className="card">
              <div className="result-head">
                <strong>{r.title}</strong>
                <span className="muted mono">{r.source_id}</span>
              </div>
              <Authors authors={r.authors} />
              <div className="muted small">
                {r.published} {r.primary_category && <span className="pill">{r.primary_category}</span>}
              </div>
              {r.summary && (
                <details>
                  <summary>Abstract</summary>
                  <p>{r.summary}</p>
                </details>
              )}
              <div className="actions">
                {row.paper ? (
                  <Link to={`/paper/${idPath(row.paper.source_id)}`}>In library — open</Link>
                ) : (
                  <>
                    <button disabled={row.busy} onClick={() => add(r, false)}>
                      Add to library
                    </button>
                    <button disabled={row.busy} onClick={() => add(r, true)}>
                      Add + PDF
                    </button>
                  </>
                )}
                {row.busy && <span className="muted">Working…</span>}
                <ErrorText error={row.error} />
              </div>
            </li>
          )
        })}
      </ul>
    </section>
  )
}
