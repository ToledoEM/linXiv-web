import {
  lazy,
  Suspense,
  useCallback,
  useEffect,
  useMemo,
  useState,
  type CSSProperties,
  type FormEvent,
  type KeyboardEvent as ReactKeyboardEvent,
  type PointerEvent as ReactPointerEvent,
} from 'react'
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom'
import { api, pdfUrl } from '../api'
import type { Annotation, Paper, PaperVersions, TagSuggestion } from '../types'
import { Authors, ErrorText } from '../components'
import { paperJournal, paperLabel, validDoi } from '../format'
import { useAiEnabled } from '../aiEnabled'
import AiSummary from '../AiSummary'
import Highlights from '../Highlights'
import MetadataEditor from '../MetadataEditor'
import Notes from '../Notes'
import TagSuggestions from '../TagSuggestions'
import { toggled } from '../projects'
import CopyToMine from '../CopyToMine'
import { useLibrary } from '../library'
import { AddToProjectBar, UndoDeleteButton } from '../projectParts'
import { MathText } from '../tex'

// pdf.js is large: load the reader only when a PDF is opened.
const PdfReader = lazy(() => import('../PdfReader'))

// Width of the PDF pane (left of the details rail), per browser.
const SPLIT_KEY = 'lxw.paperPdfSplit'
const SPLIT_DEFAULT = 68
const SPLIT_MIN = 25
const SPLIT_MAX = 75
const SPLIT_STEP = 2

const clampSplit = (pct: number) => Math.min(SPLIT_MAX, Math.max(SPLIT_MIN, Math.round(pct)))

function loadSplit(): number {
  try {
    const raw = localStorage.getItem(SPLIT_KEY)
    const n = raw ? Number.parseFloat(raw) : NaN
    return Number.isFinite(n) ? clampSplit(n) : SPLIT_DEFAULT
  } catch {
    return SPLIT_DEFAULT
  }
}

function saveSplit(value: string): void {
  try {
    localStorage.setItem(SPLIT_KEY, String(Number.parseFloat(value)))
  } catch {
    // storage unavailable: keep the dragged width for this page view only
  }
}

type Tab = 'details' | 'notes' | 'annotations'

export default function PaperDetail() {
  const id = useParams()['*'] ?? ''
  const navigate = useNavigate()
  // Opened from a project page: new notes default to that project's scope.
  const fromProjectId = (useLocation().state as { fromProjectId?: number } | null)?.fromProjectId ?? null
  const [paper, setPaper] = useState<Paper | null>(null)
  const [versions, setVersions] = useState<PaperVersions | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState('')
  const [newTag, setNewTag] = useState('')
  const aiOn = useAiEnabled()
  const library = useLibrary()
  // Shared library for a non-admin: read and copy only.
  const ro = !library.canWrite
  const [suggested, setSuggested] = useState<TagSuggestion[] | null>(null)
  const [pickedTags, setPickedTags] = useState<Set<string>>(new Set())
  const [customUrl, setCustomUrl] = useState('')
  const [showPdf, setShowPdf] = useState(true)
  // Paper whose PDF is listed but did not load (missing on disk, unreadable).
  const [pdfFailedFor, setPdfFailedFor] = useState<string | null>(null)
  // Paper whose PDF answered the preflight check; the reader mounts only then.
  const [pdfOkFor, setPdfOkFor] = useState<string | null>(null)
  const [pdfRetry, setPdfRetry] = useState(0)
  const [editingMeta, setEditingMeta] = useState(false)
  const [sourceNote, setSourceNote] = useState('')
  const [annotations, setAnnotations] = useState<Annotation[]>([])
  const [tab, setTab] = useState<Tab>('details')
  const [noteCount, setNoteCount] = useState<number | null>(null)
  const [backProject, setBackProject] = useState<string | null>(null)
  // Bumped after an AI summary is saved so the Notes panel reloads.
  const [notesTick, setNotesTick] = useState(0)
  // The one paper, in the shape AddToProjectBar expects; stable so it keeps its picker state.
  const selectedId = paper?.source_id ?? ''
  const paperSelection = useMemo(() => new Set(selectedId ? [selectedId] : []), [selectedId])

  const [initialSplit] = useState(loadSplit)

  // Split width is written straight to the CSS variable while dragging: putting it in
  // React state would re-render (and re-measure the reader) on every pointer move.
  const startDrag = useCallback((e: ReactPointerEvent<HTMLDivElement>) => {
    const section = e.currentTarget.parentElement
    if (!section) return
    e.preventDefault()
    const move = (ev: PointerEvent) => {
      const box = section.getBoundingClientRect()
      const left = ((ev.clientX - box.left) / box.width) * 100
      section.style.setProperty('--paper-split', `${clampSplit(left)}%`)
    }
    const up = () => {
      window.removeEventListener('pointermove', move)
      window.removeEventListener('pointerup', up)
      saveSplit(section.style.getPropertyValue('--paper-split'))
    }
    window.addEventListener('pointermove', move)
    window.addEventListener('pointerup', up)
  }, [])

  const keyDrag = useCallback((e: ReactKeyboardEvent<HTMLDivElement>) => {
    const section = e.currentTarget.parentElement
    if (!section) return
    const cur = Number.parseFloat(section.style.getPropertyValue('--paper-split')) || SPLIT_DEFAULT
    const next =
      e.key === 'ArrowLeft'
        ? cur - SPLIT_STEP
        : e.key === 'ArrowRight'
          ? cur + SPLIT_STEP
          : e.key === 'Home'
            ? SPLIT_MIN
            : e.key === 'End'
              ? SPLIT_MAX
              : null
    if (next === null) return
    e.preventDefault()
    const value = `${clampSplit(next)}%`
    section.style.setProperty('--paper-split', value)
    e.currentTarget.setAttribute('aria-valuenow', String(clampSplit(next)))
    saveSplit(value)
  }, [])

  const loadAnnotations = useCallback(
    () =>
      api
        .annotations(id)
        .then(setAnnotations)
        .catch(() => setAnnotations([])),
    [id],
  )

  useEffect(() => {
    void loadAnnotations()
  }, [loadAnnotations])

  useEffect(() => {
    if (fromProjectId == null) return
    let cancelled = false
    api.project(fromProjectId).then(
      (p) => !cancelled && setBackProject(p.name),
      () => {},
    )
    return () => {
      cancelled = true
    }
  }, [fromProjectId])

  const load = useCallback(
    () =>
      api.paper(id).then(
        async (p) => {
          setPaper(p)
          const v = await api.versions(id).catch(() => null)
          setVersions(v)
          setError('')
        },
        (err: Error) => setError(err.message),
      ),
    [id],
  )

  useEffect(() => {
    void load()
  }, [load])

  // Check the file is there before pdf.js asks for it: on a 404 pdf.js throws an
  // uncaught ResponseException even with an error handler set.
  const checkSid = paper?.has_pdf && showPdf ? paper.source_id : null
  useEffect(() => {
    if (!checkSid || pdfOkFor === checkSid || pdfFailedFor === checkSid) return
    const ctl = new AbortController()
    fetch(pdfUrl(checkSid), { headers: { Range: 'bytes=0-0' }, credentials: 'same-origin', signal: ctl.signal })
      .then((res) => {
        if (res.status === 404) setPdfFailedFor(checkSid)
        else setPdfOkFor(checkSid)
        void res.body?.cancel()
      })
      .catch(() => {
        if (!ctl.signal.aborted) setPdfOkFor(checkSid)
      })
    return () => ctl.abort()
  }, [checkSid, pdfOkFor, pdfFailedFor, pdfRetry])

  const act = async (label: string, fn: () => Promise<unknown>) => {
    setBusy(label)
    setError('')
    try {
      await fn()
      await load()
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setBusy('')
    }
  }

  const addTag = (e: FormEvent) => {
    e.preventDefault()
    const tags = newTag.split(',').map((t) => t.trim()).filter(Boolean)
    if (tags.length) void act('tags', () => api.addTags(id, tags)).then(() => setNewTag(''))
  }

  const suggestTags = () =>
    act('suggest', async () => {
      setSuggested(null)
      const r = await api.suggestTags(id)
      setSuggested(r.suggested)
      setPickedTags(new Set(r.suggested.map((s) => s.tag)))
    })

  const addSuggested = () => act('tags', () => api.addTags(id, [...pickedTags])).then(() => setSuggested(null))

  const deletePaper = async () => {
    setBusy('delete')
    try {
      await api.deletePaper(id)
      void navigate('/library')
    } catch (err) {
      setError((err as Error).message)
      setBusy('')
    }
  }

  const downloadPdf = () =>
    act('pdf', async () => {
      await api.downloadPdf(id, customUrl.trim() || undefined)
      setPdfFailedFor(null)
      setPdfOkFor(null)
    })

  const downloadForm = ro ? null : (
    <div className="actions">
      <button disabled={!!busy} onClick={downloadPdf}>
        {busy === 'pdf' ? 'Downloading…' : 'Download PDF'}
      </button>
      <input
        className="grow"
        aria-label="PDF URL"
        placeholder="optional PDF URL (needed for non-arXiv papers)"
        value={customUrl}
        onChange={(e) => setCustomUrl(e.target.value)}
      />
    </div>
  )

  if (!paper) return error ? <ErrorText error={error} /> : <p className="muted">Loading…</p>
  const sid = paper.source_id
  const summary = paper.summary ?? versions?.versions[0]?.summary
  const pdfFailed = pdfFailedFor === sid
  const showAnnotations = paper.has_pdf || annotations.length > 0
  const activeTab = tab === 'annotations' && !showAnnotations ? 'details' : tab

  const tabButton = (key: Tab, label: string, count?: number | null) => (
    <button
      type="button"
      role="tab"
      id={`paper-tab-${key}`}
      aria-controls={`paper-panel-${key}`}
      aria-selected={activeTab === key}
      className={activeTab === key ? 'tab active' : 'tab'}
      onClick={() => setTab(key)}
    >
      {label}
      {count != null && <span className="paper-tab-count"> {count}</span>}
    </button>
  )

  return (
    <section className="paper-view" style={{ '--paper-split': `${initialSplit}%` } as CSSProperties}>
      <div className="paper-surface" aria-label="PDF reader">
        {paper.has_pdf && showPdf && !pdfFailed && pdfOkFor !== sid ? (
          <p className="muted center pdf-status">Loading PDF…</p>
        ) : paper.has_pdf && showPdf && !pdfFailed ? (
          <Suspense fallback={<p className="muted center pdf-status">Loading viewer…</p>}>
            <PdfReader
              key={sid}
              file={pdfUrl(sid)}
              errorUrl={pdfUrl(sid)}
              sourceId={sid}
              version={paper.version}
              projectId={fromProjectId}
              annotations={annotations}
              onAnnotationsChanged={loadAnnotations}
              onLoadError={() => setPdfFailedFor(sid)}
            />
          </Suspense>
        ) : (
          <div className="paper-empty">
            {paper.has_pdf && pdfFailed ? (
              <div className="card">
                <span className="paper-empty-title">PDF not found</span>
                <p className="muted small">
                  The library lists a PDF for this paper, but the file could not be loaded. Download it again.
                </p>
                {downloadForm}
                <div className="actions">
                  <button
                    type="button"
                    className="link"
                    onClick={() => {
                      setPdfFailedFor(null)
                      setPdfOkFor(null)
                      setPdfRetry((n) => n + 1)
                    }}
                  >
                    Try again
                  </button>
                </div>
              </div>
            ) : paper.has_pdf ? (
              <div className="card">
                <span className="paper-empty-title">PDF hidden</span>
                <p className="muted small">The reader is closed. Your highlights stay in the Annotations tab.</p>
                <div className="actions">
                  <button onClick={() => setShowPdf(true)}>View PDF</button>
                </div>
              </div>
            ) : (
              <div className="card">
                <span className="paper-empty-title">No PDF stored</span>
                <p className="muted small">arXiv papers download directly. For other sources paste a PDF link.</p>
                {downloadForm}
              </div>
            )}
          </div>
        )}
      </div>

      <div
        className="paper-split-handle"
        onPointerDown={startDrag}
        onKeyDown={keyDrag}
        role="separator"
        aria-orientation="vertical"
        aria-label="Resize PDF and details"
        aria-valuemin={SPLIT_MIN}
        aria-valuemax={SPLIT_MAX}
        aria-valuenow={initialSplit}
        tabIndex={0}
        title="Drag or use arrow keys to resize"
      />

      <aside className="paper-rail" aria-label="Paper details">
        <header className="paper-rail-head">
          <div className="paper-rail-top">
            {fromProjectId != null ? (
              <Link className="paper-back" to={`/projects/${fromProjectId}`}>
                ← {backProject ?? 'Project'}
              </Link>
            ) : (
              <Link className="paper-back" to="/library">
                ← Library
              </Link>
            )}
            <span className="mono muted paper-id">{sid}</span>
            {!editingMeta && !ro && (
              <button
                type="button"
                className="link"
                onClick={() => {
                  setEditingMeta(true)
                  setTab('details')
                }}
              >
                Edit metadata
              </button>
            )}
          </div>
          <h2 className="paper-rail-title">
            {paper.title?.trim() ? (
              <MathText forceInline>{paper.title}</MathText>
            ) : (
              <span className="muted">{paperLabel(paper)}</span>
            )}
          </h2>
          {paper.authors.length > 0 && (
            <div>
              <div className="paper-label">Authors</div>
              <Authors authors={paper.authors} max={50} />
            </div>
          )}
          <div className="paper-facts">
            {paper.published && <span title="Published">{paper.published}</span>}
            {paper.updated && paper.updated !== paper.published && (
              <span className="muted">· updated {paper.updated}</span>
            )}
            {paper.categories?.map((c) => (
              <span key={c} className="pill" title="Category">
                {c}
              </span>
            ))}
            <span className="pill paper-pill-ver" title="Version">
              v{paper.version}
              {versions && versions.versions.length > 1 && (
                <span className="muted"> · {versions.versions.map((v) => `v${v.version}`).join(', ')} stored</span>
              )}
            </span>
          </div>
          <div>
            <div className="paper-label">Tags</div>
            {paper.tags.length > 0 && (
              <div className="tags">
                {paper.tags.map((t) => (
                  <span key={t} className="pill">
                    {t}
                    {!ro && (
                      <button
                        className="pill-x"
                        title={`Remove ${t}`}
                        aria-label={`Remove ${t}`}
                        disabled={!!busy}
                        onClick={() => act('tags', () => api.removeTag(id, t))}
                      >
                        ×
                      </button>
                    )}
                  </span>
                ))}
              </div>
            )}
            {!ro && (
              <form onSubmit={addTag} className="paper-tagform">
                <input
                  aria-label="Add tags"
                  placeholder="add tags, comma separated"
                  value={newTag}
                  onChange={(e) => setNewTag(e.target.value)}
                />
                <button disabled={!!busy || !newTag.trim()}>Add</button>
                {aiOn && (
                  <button type="button" disabled={!!busy} onClick={suggestTags}>
                    {busy === 'suggest' ? 'Suggesting…' : 'AI Tags'}
                  </button>
                )}
              </form>
            )}
            {suggested && (
              <div className="tag-suggest card">
                <span className="muted small">AI suggestions: click to toggle, then add the ticked ones.</span>
                <TagSuggestions
                  suggestions={suggested}
                  picked={pickedTags}
                  disabled={!!busy}
                  onToggle={(t) => setPickedTags((s) => toggled(s, t))}
                />
                <div className="actions">
                  {suggested.length > 0 && (
                    <button type="button" disabled={!!busy || !pickedTags.size} onClick={addSuggested}>
                      Add {pickedTags.size} tag{pickedTags.size === 1 ? '' : 's'}
                    </button>
                  )}
                  <button type="button" className="link" disabled={!!busy} onClick={() => setSuggested(null)}>
                    Dismiss
                  </button>
                </div>
              </div>
            )}
          </div>
          <ErrorText error={error} />
        </header>

        <div className="tabs paper-tabs" role="tablist" aria-label="Paper details">
          {tabButton('details', 'Details')}
          {tabButton('notes', 'Notes', noteCount)}
          {showAnnotations && tabButton('annotations', 'Annotations', annotations.length)}
        </div>

        <div
          className="paper-panel detail"
          role="tabpanel"
          id="paper-panel-details"
          aria-labelledby="paper-tab-details"
          hidden={activeTab !== 'details'}
        >
          {editingMeta ? (
            <>
              <h3>Edit metadata</h3>
              <MetadataEditor
                paper={paper}
                onSaved={async () => {
                  setEditingMeta(false)
                  await load()
                }}
                onCancel={() => setEditingMeta(false)}
              />
            </>
          ) : (
            <>
              {summary && (
                <>
                  <h3>Abstract</h3>
                  <p className="abstract">
                    <MathText>{summary}</MathText>
                  </p>
                </>
              )}
              {(validDoi(paper.doi) || paperJournal(paper) || paper.comment || paper.url) && (
                <dl className="meta">
                  {validDoi(paper.doi) && (
                    <>
                      <dt>DOI</dt>
                      <dd className="mono">{validDoi(paper.doi)}</dd>
                    </>
                  )}
                  {paperJournal(paper) && (
                    <>
                      <dt>Journal</dt>
                      <dd>{paperJournal(paper)}</dd>
                    </>
                  )}
                  {paper.comment && (
                    <>
                      <dt>Comment</dt>
                      <dd>{paper.comment}</dd>
                    </>
                  )}
                  {paper.url && (
                    <>
                      <dt>Link</dt>
                      <dd>
                        <a href={paper.url} target="_blank" rel="noreferrer noopener">
                          {paper.url}
                        </a>
                      </dd>
                    </>
                  )}
                </dl>
              )}
            </>
          )}

          {library.shared && (
            <details className="paper-section" open>
              <summary>Shared library</summary>
              <div className="actions">
                <CopyToMine ids={[sid]} />
              </div>
            </details>
          )}

          {!ro && (
            <details className="paper-section" open>
              <summary>Projects</summary>
              <AddToProjectBar inline selected={paperSelection} onSelect={() => {}} />
            </details>
          )}

          {aiOn && !ro && (
            <details className="paper-section" open>
              <summary>AI summary</summary>
              <AiSummary
                key={sid}
                sourceId={sid}
                hasPdf={paper.has_pdf}
                projectId={fromProjectId}
                onSaved={() => setNotesTick((n) => n + 1)}
              />
            </details>
          )}

          <details className="paper-section" open>
            <summary>PDF</summary>
            {paper.pdf_file && (
              <p className="muted small">
                File: <span className="mono">{paper.pdf_file}</span>
              </p>
            )}
            {paper.has_pdf ? (
              <div className="actions">
                <button onClick={() => setShowPdf((s) => !s)}>{showPdf ? 'Hide PDF' : 'View PDF'}</button>
                <a href={pdfUrl(sid)} target="_blank" rel="noreferrer">
                  Open in new tab
                </a>
                {!ro && (
                  <UndoDeleteButton label="Delete PDF" busy={!!busy} onConfirm={() => act('pdf', () => api.deletePdf(id))} />
                )}
              </div>
            ) : (
              <p className="muted small">No PDF stored. Download it from the reader area.</p>
            )}
          </details>

          {!ro && (sid.startsWith('arxiv:') || paper.has_pdf) && (
            <details className="paper-section" open>
              <summary>Full text</summary>
              <p className="muted small">
                {paper.downloaded_source
                  ? 'Full text indexed: Full text search in the Library covers this paper.'
                  : 'Not indexed: Full text search can’t find words inside this paper yet.'}
              </p>
              <div className="actions">
                {sid.startsWith('arxiv:') && (
                  <button
                    disabled={!!busy}
                    onClick={() =>
                      act('source', async () => {
                        const r = await api.fetchSource(id, !!paper.downloaded_source)
                        setSourceNote(r.indexed ? `Indexed ${r.chars ?? 0} characters.` : (r.reason ?? 'Nothing to index.'))
                      })
                    }
                  >
                    {busy === 'source' ? 'Fetching…' : paper.downloaded_source ? 'Re-fetch TeX source' : 'Fetch TeX source'}
                  </button>
                )}
                {paper.has_pdf && (
                  <button
                    disabled={!!busy}
                    title={
                      sid.startsWith('arxiv:')
                        ? 'For submissions without TeX source; replaces any indexed TeX text.'
                        : undefined
                    }
                    onClick={() =>
                      act('pdf-text', async () => {
                        const r = await api.indexPdfText(id)
                        setSourceNote(
                          `Indexed ${r.chars ?? 0} characters from the PDF${r.truncated ? ' (long PDF: first part only)' : ''}.`,
                        )
                      })
                    }
                  >
                    {busy === 'pdf-text' ? 'Reading PDF…' : 'Index PDF text'}
                  </button>
                )}
              </div>
              {sourceNote && <p className="small">{sourceNote}</p>}
            </details>
          )}

          {!ro && (
            <details className="paper-section">
              <summary>Danger zone</summary>
              <div className="actions">
                <UndoDeleteButton label="Delete paper" busy={!!busy} onConfirm={deletePaper} />
                <span className="muted small">Moves the paper to the trash.</span>
              </div>
            </details>
          )}
        </div>

        <div
          className="paper-panel"
          role="tabpanel"
          id="paper-panel-notes"
          aria-labelledby="paper-tab-notes"
          hidden={activeTab !== 'notes'}
        >
          <Notes
            key={`${sid}:${notesTick}`}
            sourceId={sid}
            defaultProjectId={fromProjectId}
            paper={paper}
            onCount={setNoteCount}
          />
        </div>

        {showAnnotations && (
          <div
            className="paper-panel"
            role="tabpanel"
            id="paper-panel-annotations"
            aria-labelledby="paper-tab-annotations"
            hidden={activeTab !== 'annotations'}
          >
            <Highlights annotations={annotations} sourceId={sid} version={paper.version} onChanged={loadAnnotations} />
          </div>
        )}
      </aside>
    </section>
  )
}
