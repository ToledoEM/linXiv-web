import { useEffect, useRef, useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { api, paperPath } from '../api'
import type { Paper, SearchResult, Source } from '../types'
import { Authors, ErrorText } from '../components'
import { addTerm, DEFAULT_HISTORY_MAX } from '../searchHistory'
import QueryBuilder from '../QueryBuilder'
import { makeClause, type Clause } from '../searchQuery'
import SuggestInput from '../SuggestInput'
import { useLibrary } from '../library'
import { MathText } from '../tex'

type RowState = { busy?: boolean; paper?: Paper; error?: string }
type Tab = Source | 'local'
type ViewSort = 'relevance' | 'newest' | 'oldest'

const TABS: { value: Tab; label: string }[] = [
  { value: 'arxiv', label: 'arXiv' },
  { value: 'openalex', label: 'OpenAlex' },
  { value: 'crossref', label: 'Crossref' },
  { value: 'local', label: 'Local' },
]
const MAX_OPTIONS = [10, 25, 50, 100]

// The CLI has no sort flag for search, so results are re-ordered here.
// Undated entries go last under newest and first under oldest (as on desktop).
function sortResults(results: SearchResult[], sort: ViewSort): SearchResult[] {
  if (sort === 'relevance') return results
  const key = (r: SearchResult) => r.published ?? '0000-00-00'
  const sorted = [...results].sort((a, b) => key(a).localeCompare(key(b)))
  return sort === 'newest' ? sorted.reverse() : sorted
}

function asResult(p: Paper): SearchResult {
  return {
    source_id: p.source_id,
    version: p.version,
    title: p.title,
    summary: p.summary,
    authors: p.authors,
    published: p.published,
    primary_category: p.category ?? undefined,
  }
}

export default function Search() {
  const { canWrite } = useLibrary()
  const [q, setQ] = useState('')
  const [source, setSource] = useState<Tab>('arxiv')
  const [max, setMax] = useState(25)
  const [sort, setSort] = useState<ViewSort>('relevance')
  const [results, setResults] = useState<SearchResult[] | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [rows, setRows] = useState<Record<string, RowState>>({})
  // linXiv settings `search_history_enabled` / `search_history_max` (desktop Settings → Search).
  const [history, setHistory] = useState({ enabled: true, max: DEFAULT_HISTORY_MAX })
  // Advanced clause builder: arXiv query syntax, so arXiv tab only (desktop parity).
  const [advancedOpen, setAdvancedOpen] = useState(false)
  const [clauses, setClauses] = useState<Clause[]>(() => [makeClause()])
  // A built query was already recorded clause by clause; don't store the syntax string too.
  const insertedRef = useRef('')

  useEffect(() => {
    api
      .settings()
      .then((r) => setHistory({ enabled: r.settings.search_history_enabled, max: r.settings.search_history_max }))
      .catch(() => {})
  }, [])

  const run = async (tab: Tab) => {
    if (!q.trim()) return
    if (history.enabled && q.trim() !== insertedRef.current) addTerm(q, history.max)
    setBusy(true)
    setError('')
    setRows({})
    try {
      if (tab === 'local') {
        // Library papers: every row is already saved, so it links straight to it.
        const papers = await api.papers({ q: q.trim(), limit: 500 })
        setRows(Object.fromEntries(papers.map((p) => [p.source_id, { paper: p }])))
        setResults(papers.map(asResult))
      } else {
        setResults(await api.search(q.trim(), tab, max))
      }
    } catch (err) {
      setError(String((err as Error).message))
      setResults(null)
    } finally {
      setBusy(false)
    }
  }

  const submit = (e: FormEvent) => {
    e.preventDefault()
    void run(source)
  }

  const insertQuery = (query: string) => {
    // Desktop records each clause term, not the built query string.
    if (history.enabled) for (const c of clauses) addTerm(c.value, history.max)
    insertedRef.current = query
    setQ(query)
    setAdvancedOpen(false)
  }

  const switchTab = (tab: Tab) => {
    setSource(tab)
    if (tab !== 'arxiv') setAdvancedOpen(false)
    setResults(null)
    if (q.trim()) void run(tab)
  }

  const add = async (r: SearchResult, withPdf: boolean) => {
    if (source === 'local') return
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
      <div className="tabs" role="tablist" aria-label="Source">
        {TABS.map((t) => (
          <button
            key={t.value}
            role="tab"
            aria-selected={source === t.value}
            className={source === t.value ? 'tab active' : 'tab'}
            onClick={() => switchTab(t.value)}
            disabled={busy}
          >
            {t.label}
          </button>
        ))}
      </div>
      <form className="toolbar" onSubmit={submit}>
        <SuggestInput
          aria-label="Search query"
          placeholder={
            source === 'local' ? 'Search your library: title, abstract, author, full text, notes…' : 'Title, author, keywords…'
          }
          value={q}
          onValueChange={setQ}
          enabled={history.enabled}
          autoFocus
        />
        {source !== 'local' && (
          <select aria-label="Maximum results" value={max} onChange={(e) => setMax(Number(e.target.value))}>
            {MAX_OPTIONS.map((n) => (
              <option key={n} value={n}>
                {n} results
              </option>
            ))}
          </select>
        )}
        <select aria-label="Sort results" value={sort} onChange={(e) => setSort(e.target.value as ViewSort)}>
          <option value="relevance">Relevance</option>
          <option value="newest">Newest first</option>
          <option value="oldest">Oldest first</option>
        </select>
        <button disabled={busy}>{busy ? 'Searching…' : 'Search'}</button>
        {source === 'arxiv' && (
          <button
            type="button"
            className="link"
            aria-expanded={advancedOpen}
            onClick={() => setAdvancedOpen((v) => !v)}
          >
            Advanced {advancedOpen ? '▴' : '▾'}
          </button>
        )}
      </form>
      {source === 'arxiv' && advancedOpen && (
        <QueryBuilder clauses={clauses} onChange={setClauses} onInsert={insertQuery} historyEnabled={history.enabled} />
      )}
      <ErrorText error={error} />
      {results && (
        <p className="muted small">
          {results.length} result{results.length === 1 ? '' : 's'}
        </p>
      )}
      <ul className="results">
        {results && sortResults(results, sort).map((r) => {
          const row = rows[r.source_id] ?? {}
          return (
            <li key={r.entry_id ?? r.source_id} className="card">
              <div className="result-head">
                <strong>
                  <MathText forceInline>{r.title}</MathText>
                </strong>
                <span className="muted mono">{r.source_id}</span>
              </div>
              <Authors authors={r.authors} />
              <div className="muted small">
                {r.published} {r.primary_category && <span className="pill">{r.primary_category}</span>}
              </div>
              {r.summary && (
                <details>
                  <summary>Abstract</summary>
                  <p>
                    <MathText>{r.summary}</MathText>
                  </p>
                </details>
              )}
              <div className="actions">
                {row.paper ? (
                  <Link to={paperPath(row.paper.source_id)}>In library — open</Link>
                ) : !canWrite ? (
                  <span className="muted small">Switch to My library to add papers.</span>
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
