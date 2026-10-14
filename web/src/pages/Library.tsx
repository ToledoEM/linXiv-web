import { useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { api, idPath, saveBlob } from '../api'
import type { Paper } from '../types'
import { useAiEnabled } from '../aiEnabled'
import BatchMetadata from '../BatchMetadata'
import BatchTags from '../BatchTags'
import { DoiLine, ErrorText, Pager, PaperColGroup, SortHeader, TagCell } from '../components'
import { paperLabel } from '../format'
import { loadSort, nextSort, parsePaperSort, saveSort, type PaperSort, type PaperSortKey } from '../paperSort'
import { AddToProjectBar } from '../projectParts'
import { toggled } from '../projects'
import { PAGE_SIZES, tableMinWidth, useTableColumns } from '../tableColumns'
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

export default function Library() {
  const [q, setQ] = useState('')
  const [params] = useSearchParams()
  const [tag, setTag] = useState(() => (params.get('untagged') ? UNTAGGED : (params.get('tag') ?? '')))
  const [deepError, setDeepError] = useState('')
  const [stored] = useState(() => loadSort(SORT_KEY, parseStored, { server: SORTS[0].value, column: null }))
  const [sort, setSort] = useState<string>(stored.server)
  const [column, setColumn] = useState<PaperSort | null>(stored.column)
  const [pdf, setPdf] = useState<PdfFilter>('all')
  const [tags, setTags] = useState<string[]>([])
  const [papers, setPapers] = useState<Paper[] | null>(null)
  const [error, setError] = useState('')
  const [selected, setSelected] = useState<Set<string>>(new Set())
  // Batch edit metadata: panel beside the table, driven by the row selection.
  const [batch, setBatch] = useState(false)
  // Batch panel content: metadata lookup, or AI tag suggestions (when AI is on).
  const [batchMode, setBatchMode] = useState<'metadata' | 'tags'>('metadata')
  const aiOn = useAiEnabled()
  const cols = useTableColumns()
  const mode = aiOn ? batchMode : 'metadata'
  const [reload, setReload] = useState(0)
  const [size, setSize] = useState(loadPageSize)
  const [total, setTotal] = useState(NaN)
  const [seen, setSeen] = useState<Record<string, string>>({})

  useEffect(() => {
    api
      .allTags()
      .then(setTags)
      .catch(() => setTags([]))
  }, [])

  // Any filter or sort change goes back to page 1 (no extra fetch: the page is
  // keyed to the query it belongs to).
  const query = JSON.stringify([q.trim(), tag, sort, column, pdf, size])
  const [paging, setPaging] = useState({ query, page: 1 })
  // Deleting or untagging papers can shrink the result below the current page.
  const lastPage = Number.isFinite(total) ? Math.max(1, Math.ceil(total / size)) : Infinity
  const page = Math.min(paging.query === query ? paging.page : 1, lastPage)
  const goTo = (n: number) => setPaging({ query, page: n })

  useEffect(() => {
    let cancelled = false
    const t = setTimeout(() => {
      const [by, dir] = column ? [column.key, column.dir] : (sort.split('_') as [string, 'asc' | 'desc'])
      api
        .papers(
          {
            q: q.trim() || undefined,
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
    }, 250)
    return () => {
      cancelled = true
      clearTimeout(t)
    }
  }, [q, tag, sort, column, pdf, page, size, reload])

  useEffect(() => saveSort(SORT_KEY, { server: sort, column }), [sort, column])

  const [serverBy, serverDir] = sort.split('_') as [string, 'asc' | 'desc']
  const headerDir = (key: PaperSortKey) =>
    column ? (column.key === key ? column.dir : null) : SERVER_KEYS[key] === serverBy ? serverDir : null
  const sortBy = (key: PaperSortKey) => {
    const next = nextSort(
      column ?? (SERVER_KEYS[serverBy as PaperSortKey] ? { key: serverBy as PaperSortKey, dir: serverDir } : null),
      key,
    )
    if (SERVER_KEYS[key]) {
      setColumn(null)
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
      <p className="muted small library-count">{papers ? `${count} paper${count === 1 ? '' : 's'}` : '\u00a0'}</p>
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
        <button
          type="button"
          className={batch ? 'batch-toggle active' : 'batch-toggle'}
          aria-pressed={batch}
          onClick={() => setBatch((b) => !b)}
        >
          batch edit
        </button>
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
            setColumn(null)
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
        <input
          className="grow"
          type="search"
          aria-label="Search library"
          placeholder="Search by title, abstract, author, id, full text or notes…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
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
      <AddToProjectBar selected={selected} onSelect={setSelected} extra={<ExportBibButton ids={selected} />} />
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
                        <Link to={`/paper/${idPath(p.source_id)}`}>
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
          {papers && count > 0 && (
            <Pager
              page={page}
              size={size}
              total={count}
              onPage={goTo}
              onSize={(n) => {
                setSize(n)
                savePageSize(n)
              }}
            />
          )}
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
