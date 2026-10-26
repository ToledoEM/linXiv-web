import { useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { api, paperPath, saveBlob } from '../api'
import type { Paper } from '../types'
import { useAiEnabled } from '../aiEnabled'
import BatchMetadata from '../BatchMetadata'
import BatchTags from '../BatchTags'
import CopyToMine from '../CopyToMine'
import { DoiLine, ErrorText, Pager, PaperColGroup, SortHeader, TagCell } from '../components'
import { paperLabel } from '../format'
import { loadSort, nextSort, parsePaperSort, saveSort, type PaperSort, type PaperSortKey } from '../paperSort'
import { AddToProjectBar } from '../projectParts'
import { toggled } from '../projects'
import { PAGE_SIZES, tableMinWidth, useTableColumns } from '../tableColumns'
import { useLibrary } from '../library'
import { MathText } from '../tex'

/** Selection bar action: BibTeX for the selected papers. */
function ExportBibButton({ ids }: { ids: Set<string> }) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const run = async () => {
    setBusy(true)
    setError('')
    try {
      saveBlob(await api.exportBibtex([...ids]), 'linxiv-selection.bib')
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setBusy(false)
    }
  }
  return (
    <>
      <button onClick={run} disabled={busy} title="Download a BibTeX file for the selected papers">
        {busy ? 'Exporting…' : 'Export .bib'}
      </button>
      {error && <span className="error small">{error}</span>}
    </>
  )
}

type PdfFilter = 'all' | 'has' | 'none'

const PDF_FILTERS: { value: PdfFilter; label: string }[] = [
  { value: 'all', label: 'All' },
  { value: 'has', label: 'Has PDF' },
  { value: 'none', label: 'No PDF' },
]

// Same choices as linXiv desktop's Library.
const SORTS = [
  { value: 'published_desc', label: 'Newest first' },
  { value: 'published_asc', label: 'Oldest first' },
  { value: 'added_desc', label: 'Recently added' },
  { value: 'added_asc', label: 'First added' },
  { value: 'title_asc', label: 'Title A–Z' },
  { value: 'title_desc', label: 'Title Z–A' },
] as const

// Title / Published headers drive the sort dropdown; the other columns sort the
// whole library on the server too (`sort=authors|category|tags|pdf`).
const SERVER_KEYS: Partial<Record<PaperSortKey, string>> = { title: 'title', published: 'published' }
const SORT_KEY = 'lxw.librarySort'
const PAGE_SIZE_KEY = 'lxw.libraryPageSize'
const DEFAULT_PAGE_SIZE = 50

function loadPageSize(): number {
  try {
    const n = Number(localStorage.getItem(PAGE_SIZE_KEY))
    return PAGE_SIZES.includes(n) ? n : DEFAULT_PAGE_SIZE
  } catch {
    return DEFAULT_PAGE_SIZE
  }
}

function savePageSize(n: number): void {
  try {
    localStorage.setItem(PAGE_SIZE_KEY, String(n))
  } catch {
    // storage unavailable: the choice lasts for this page load only
  }
}
// Tag select value for papers without tags (`?untagged=1`); not a valid tag name.
const UNTAGGED = '\u0000untagged'

interface StoredSort {
  server: string
  column: PaperSort | null
}

function parseStored(raw: unknown): StoredSort {
  const r = (raw ?? {}) as Record<string, unknown>
  const server = SORTS.some((o) => o.value === r.server) ? (r.server as string) : SORTS[0].value
  const column = parsePaperSort(r.column)
  return { server, column: column && !SERVER_KEYS[column.key] ? column : null }
}

/** `col=<key>_<dir>` URL value: a column sort the dropdown has no entry for. */
function parseCol(raw: string | null): PaperSort | null {
  if (!raw) return null
  const i = raw.lastIndexOf('_')
  const col = parsePaperSort({ key: raw.slice(0, i), dir: raw.slice(i + 1) })
  return col && !SERVER_KEYS[col.key] ? col : null
}

export default function Library() {
  // List state lives in the URL (`?page=&q=&tag=|untagged=1&pdf=&sort=|col=&size=`)
  // so pages can be bookmarked, reloaded and reached with Back. Sort and page
  // size fall back to this browser's last choice when the URL has none.
  const [params, setParams] = useSearchParams()
  const [stored, setStored] = useState(() => loadSort(SORT_KEY, parseStored, { server: SORTS[0].value, column: null }))
  const [storedSize, setStoredSize] = useState(loadPageSize)
  const q = params.get('q')?.trim() ?? ''
  const tag = params.get('untagged') ? UNTAGGED : (params.get('tag') ?? '')
  const pdfParam = params.get('pdf')
  const pdf: PdfFilter = pdfParam === 'has' || pdfParam === 'none' ? pdfParam : 'all'
  const sortParam = params.get('sort')
  const urlSort = SORTS.some((o) => o.value === sortParam) ? sortParam : null
  const colParam = params.get('col')
  // Memoized: a new object each render would re-run the fetch effect forever.
  const urlCol = useMemo(() => parseCol(colParam), [colParam])
  const sort = urlSort ?? stored.server
  const column = urlSort || urlCol ? urlCol : stored.column
  const sizeParam = Number(params.get('size'))
  const size = PAGE_SIZES.includes(sizeParam) ? sizeParam : storedSize

  /** Change URL params (null removes one); any change but `page` goes back to page 1. */
  const update = (patch: Record<string, string | null>, replace = false) => {
    // Live URL, not `params`: two quick changes before a re-render would drop the first.
    const next = new URLSearchParams(window.location.search)
    for (const [k, v] of Object.entries(patch)) {
      if (v) next.set(k, v)
      else next.delete(k)
    }
    if (!('page' in patch)) next.delete('page')
    setParams(next, { replace })
  }
  const setTag = (v: string) => update({ tag: v && v !== UNTAGGED ? v : null, untagged: v === UNTAGGED ? '1' : null })
  const setPdf = (v: PdfFilter) => update({ pdf: v === 'all' ? null : v })
  const setSort = (v: string) => {
    setStored({ server: v, column: null })
    saveSort(SORT_KEY, { server: v, column: null })
    update({ sort: v, col: null })
  }
  const setColumn = (c: PaperSort) => {
    setStored({ server: sort, column: c })
    saveSort(SORT_KEY, { server: sort, column: c })
    update({ col: `${c.key}_${c.dir}` })
  }
  const setSize = (n: number) => {
    setStoredSize(n)
    savePageSize(n)
    update({ size: String(n) })
  }

  // Search box keeps its own text; only the search button writes it to the URL.
  // An outside URL change (Back, links) replaces the text in the box.
  const [draft, setDraft] = useState(q)
  const [seenQ, setSeenQ] = useState(q)
  if (q !== seenQ) {
    setSeenQ(q)
    setDraft(q)
  }
  const search = () => update({ q: draft.trim() || null })

  const [deepError, setDeepError] = useState('')
  const [tags, setTags] = useState<string[]>([])
  const [papers, setPapers] = useState<Paper[] | null>(null)
  const [error, setError] = useState('')
  const [selected, setSelected] = useState<Set<string>>(new Set())
  // Batch edit metadata: panel beside the table, driven by the row selection.
  const [batch, setBatch] = useState(false)
  // Batch panel content: metadata lookup, or AI tag suggestions (when AI is on).
  const [batchMode, setBatchMode] = useState<'metadata' | 'tags'>('metadata')
  const aiOn = useAiEnabled()
  const library = useLibrary()
  const cols = useTableColumns()
  const mode = aiOn ? batchMode : 'metadata'
  const [reload, setReload] = useState(0)
  const [total, setTotal] = useState(NaN)
  const [seen, setSeen] = useState<Record<string, string>>({})
  const [duplicates, setDuplicates] = useState(0)

  useEffect(() => {
    api
      .allTags()
      .then(setTags)
      .catch(() => setTags([]))
    api
      .duplicates()
      .then((d) => setDuplicates(d.groups.length))
      .catch(() => {})
  }, [])

  // Deleting or untagging papers can shrink the result below the current page.
  const lastPage = Number.isFinite(total) ? Math.max(1, Math.ceil(total / size)) : Infinity
  const page = Math.min(Math.max(1, Math.floor(Number(params.get('page'))) || 1), lastPage)
  const goTo = (n: number) => update({ page: n > 1 ? String(n) : null })

  useEffect(() => {
    let cancelled = false
    {
      const [by, dir] = column ? [column.key, column.dir] : (sort.split('_') as [string, 'asc' | 'desc'])
      api
        .papers(
          {
            q: q || undefined,
            tag: tag && tag !== UNTAGGED ? tag : undefined,
            untagged: tag === UNTAGGED || undefined,
            sort: by,
            dir,
            pdf: pdf === 'all' ? undefined : pdf,
            limit: size,
            offset: (page - 1) * size,
          },
          (res) => {
            if (cancelled) return
            setDeepError(res.headers.get('X-Deep-Search-Error') ?? '')
            setTotal(Number(res.headers.get('X-Total-Count') ?? NaN))
          },
        )
        .then((p) => {
          if (!cancelled) {
            setPapers(p)
            setSeen((s) => ({ ...s, ...Object.fromEntries(p.map((x) => [x.source_id, paperLabel(x)])) }))
            setError('')
          }
        })
        .catch((err) => !cancelled && setError((err as Error).message))
    }
    return () => {
      cancelled = true
    }
  }, [q, tag, sort, column, pdf, page, size, reload])

  const [serverBy, serverDir] = sort.split('_') as [string, 'asc' | 'desc']
  const headerDir = (key: PaperSortKey) =>
    column ? (column.key === key ? column.dir : null) : SERVER_KEYS[key] === serverBy ? serverDir : null
  const sortBy = (key: PaperSortKey) => {
    const next = nextSort(
      column ?? (SERVER_KEYS[serverBy as PaperSortKey] ? { key: serverBy as PaperSortKey, dir: serverDir } : null),
      key,
    )
    if (SERVER_KEYS[key]) {
      setSort(`${SERVER_KEYS[key]}_${next.dir}`)
    } else {
      setColumn(next)
    }
  }

  const allShownSelected = !!papers?.length && papers.every((p) => selected.has(p.source_id))
  // Batch cards follow table order; selected papers hidden by a filter go last.
  const batchIds = useMemo(() => {
    const inTable = (papers ?? []).map((p) => p.source_id).filter((sid) => selected.has(sid))
    return [...inTable, ...[...selected].filter((sid) => !inTable.includes(sid))]
  }, [papers, selected])
  // Titles of every paper seen on any page, so selections from other pages keep a label.
  const titles = seen
  const count = Number.isFinite(total) ? total : (papers?.length ?? 0)

  return (
    <section>
      <h2>Library</h2>
      <p className="muted small library-count">
        {papers ? `${count} paper${count === 1 ? '' : 's'}` : '\u00a0'}
        {duplicates > 0 && (
          <>
            {' \u00b7 '}
            <Link to="/duplicates">
              {duplicates} duplicate group{duplicates === 1 ? '' : 's'}
            </Link>
          </>
        )}
      </p>
      <div className="toolbar">
        <div className="chips" role="group" aria-label="PDF filter">
          {PDF_FILTERS.map((f) => (
            <button
              key={f.value}
              className={pdf === f.value ? 'chip active' : 'chip'}
              aria-pressed={pdf === f.value}
              onClick={() => setPdf(f.value)}
            >
              {f.label}
            </button>
          ))}
        </div>
        {library.canWrite && (
          <button
            type="button"
            className={batch ? 'batch-toggle active' : 'batch-toggle'}
            aria-pressed={batch}
            onClick={() => setBatch((b) => !b)}
          >
            batch edit
          </button>
        )}
        {batch && aiOn && (
          <div className="chips" role="group" aria-label="Batch mode">
            {(
              [
                ['metadata', 'Metadata'],
                ['tags', 'AI tags'],
              ] as const
            ).map(([value, label]) => (
              <button
                key={value}
                type="button"
                className={mode === value ? 'chip active' : 'chip'}
                aria-pressed={mode === value}
                onClick={() => setBatchMode(value)}
              >
                {label}
              </button>
            ))}
          </div>
        )}
        <span className="grow" />
        <select
          aria-label="Sort"
          value={sort}
          onChange={(e) => {
            setSort(e.target.value)
          }}
        >
          {SORTS.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
      </div>
      <div className="toolbar">
        <div className="search-box grow">
          <span className="search-field">
            <input
              type="search"
              aria-label="Search library"
              placeholder="Search by title, abstract, author, id, full text or notes…"
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
            />
            {/* Lucide "search" icon (ISC) */}
            <svg
              width="16"
              height="16"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
              aria-hidden="true"
            >
              <circle cx="11" cy="11" r="8" />
              <path d="m21 21-4.34-4.34" />
            </svg>
          </span>
          <button type="button" onClick={search}>
            Search
          </button>
        </div>
        <select aria-label="Tag" value={tag} onChange={(e) => setTag(e.target.value)}>
          <option value="">All tags</option>
          <option value={UNTAGGED}>Untagged</option>
          {tags.map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </select>
      </div>
      <ErrorText error={error} />
      {deepError && (
        <p className="muted small">Full text and notes could not be searched ({deepError}); showing other matches.</p>
      )}
      <AddToProjectBar
        selected={selected}
        onSelect={setSelected}
        readOnly={!library.canWrite}
        extra={
          <>
            <ExportBibButton ids={selected} />
            {library.shared && <CopyToMine ids={[...selected]} />}
          </>
        }
      />
      <div className={batch ? 'library-batch' : undefined}>
        <div className="library-main">
          {papers && papers.length === 0 && <p className="muted">No papers.</p>}
          {papers && papers.length > 0 && (
            <div className="table-wrap">
              <table className="paper-table" style={{ minWidth: tableMinWidth(cols) }}>
                <PaperColGroup cols={cols} />
                <thead>
                  <tr>
                    <th className="check-col">
                      <input
                        type="checkbox"
                        aria-label="Select all shown"
                        checked={allShownSelected}
                        onChange={() => {
                          const next = new Set(selected)
                          for (const p of papers) {
                            if (allShownSelected) next.delete(p.source_id)
                            else next.add(p.source_id)
                          }
                          setSelected(next)
                        }}
                      />
                    </th>
                    <SortHeader label="Title" dir={headerDir('title')} onClick={() => sortBy('title')} />
                    {cols.show.authors && (
                      <SortHeader label="Authors" dir={headerDir('authors')} onClick={() => sortBy('authors')} />
                    )}
                    {cols.show.published && (
                      <SortHeader label="Published" dir={headerDir('published')} onClick={() => sortBy('published')} />
                    )}
                    {cols.show.category && (
                      <SortHeader label="Category" dir={headerDir('category')} onClick={() => sortBy('category')} />
                    )}
                    {cols.show.tags && <SortHeader label="Tags" dir={headerDir('tags')} onClick={() => sortBy('tags')} />}
                    {cols.show.pdf && <SortHeader label="PDF" dir={headerDir('pdf')} onClick={() => sortBy('pdf')} />}
                  </tr>
                </thead>
                <tbody>
                  {papers.map((p) => (
                    <tr key={p.source_id}>
                      <td className="check-col">
                        <input
                          type="checkbox"
                          aria-label={`Select ${p.source_id}`}
                          checked={selected.has(p.source_id)}
                          onChange={() => setSelected((s) => toggled(s, p.source_id))}
                        />
                      </td>
                      <td>
                        <Link to={paperPath(p.source_id)}>
                          {p.title?.trim() ? (
                            <MathText forceInline>{p.title}</MathText>
                          ) : (
                            <span className="muted">{paperLabel(p)}</span>
                          )}
                        </Link>
                        {p.title_suspect && p.title?.trim() && (
                          <span
                            className="pill title-pill"
                            title="This title was read from the PDF and looks wrong, or unlike the file name. Batch edit can search by the file name."
                          >
                            title?
                          </span>
                        )}
                        {p.title_suspect && p.title?.trim() && p.pdf_file && (
                          <span className="muted small block mono file-line">{p.pdf_file}</span>
                        )}
                        {p.deep_match && (
                          <span className="pill deep-pill" title="Matched in the indexed full text or a note">
                            full text / notes
                          </span>
                        )}
                        {cols.doi.library && <DoiLine doi={p.doi} />}
                      </td>
                      {cols.show.authors && (
                        <td className="small">
                          {p.authors?.slice(0, 3).join(', ')}
                          {p.authors?.length > 3 && ' et al.'}
                        </td>
                      )}
                      {cols.show.published && <td className="nowrap">{p.published}</td>}
                      {cols.show.category && <td>{p.category}</td>}
                      {cols.show.tags && <TagCell tags={p.tags} />}
                      {cols.show.pdf && <td>{p.has_pdf ? '✓' : ''}</td>}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {papers && count > 0 && <Pager page={page} size={size} total={count} onPage={goTo} onSize={setSize} />}
        </div>
        {batch && mode === 'tags' && (
          <BatchTags
            selected={batchIds}
            titles={titles}
            onSaved={() => setReload((n) => n + 1)}
            onSkip={(sid) => setSelected((s) => toggled(s, sid))}
          />
        )}
        {batch && mode === 'metadata' && (
          <BatchMetadata
            selected={batchIds}
            titles={titles}
            onSaved={() => setReload((n) => n + 1)}
            onSkip={(sid) => setSelected((s) => toggled(s, sid))}
          />
        )}
      </div>
    </section>
  )
}
