import {
  lazy,
  Suspense,
  useCallback,
  useEffect,
  useMemo,
  useState,
  type CSSProperties,
  type FormEvent,
  type PointerEvent as ReactPointerEvent,
} from 'react'
import { useLocation, useNavigate, useParams } from 'react-router-dom'
import { api, pdfUrl } from '../api'
import type { Annotation, Paper, PaperVersions, TagSuggestion } from '../types'
import { Authors, ErrorText } from '../components'
import { cleanDoi, paperJournal, paperLabel } from '../format'
import { useAiEnabled } from '../aiEnabled'
import AiSummary from '../AiSummary'
import Highlights from '../Highlights'
import MetadataEditor from '../MetadataEditor'
import Notes from '../Notes'
import TagSuggestions from '../TagSuggestions'
import { toggled } from '../projects'
import { AddToProjectBar, UndoDeleteButton } from '../projectParts'
import { MathText } from '../tex'

// pdf.js is large: load the reader only when a PDF is opened.
const PdfReader = lazy(() => import('../PdfReader'))

// Width of the details column when the PDF pane is open, per browser.
const SPLIT_KEY = 'lxw.paperSplit'
const SPLIT_DEFAULT = '55%'

const clampSplit = (pct: number) => Math.min(75, Math.max(25, Math.round(pct)))

function loadSplit(): string {
  try {
    const raw = localStorage.getItem(SPLIT_KEY)
    const n = raw ? Number.parseFloat(raw) : NaN
    return Number.isFinite(n) ? `${clampSplit(n)}%` : SPLIT_DEFAULT
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
  const [suggested, setSuggested] = useState<TagSuggestion[] | null>(null)
  const [pickedTags, setPickedTags] = useState<Set<string>>(new Set())
  const [customUrl, setCustomUrl] = useState('')
  const [showPdf, setShowPdf] = useState(false)
  const [editingMeta, setEditingMeta] = useState(false)
  const [sourceNote, setSourceNote] = useState('')
  const [annotations, setAnnotations] = useState<Annotation[]>([])
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

  if (!paper) return error ? <ErrorText error={error} /> : <p className="muted">Loading…</p>
  const sid = paper.source_id

  const split = showPdf && paper.has_pdf

  return (
    <section
      className={split ? 'detail paper-split' : 'detail'}
      style={split ? ({ '--paper-split': initialSplit } as CSSProperties) : undefined}
    >
      <div className="paper-main">
      <div className="page-head">
        <h2>
          {paper.title?.trim() ? (
            <MathText forceInline>{paper.title}</MathText>
          ) : (
            <span className="muted">{paperLabel(paper)}</span>
          )}
        </h2>
        {!editingMeta && (
          <button className="page-head-action" onClick={() => setEditingMeta(true)}>
            Edit metadata
          </button>
        )}
      </div>
      <Authors authors={paper.authors} max={50} />
      {editingMeta ? (
        <MetadataEditor
          paper={paper}
          onSaved={async () => {
            setEditingMeta(false)
            await load()
          }}
          onCancel={() => setEditingMeta(false)}
        />
      ) : (
        <>
          <dl className="meta">
            <dt>ID</dt>
            <dd className="mono">{sid}</dd>
            <dt>Version</dt>
            <dd>
              v{paper.version}
              {versions && versions.versions.length > 1 && (
                <span className="muted"> ({versions.versions.map((v) => `v${v.version}`).join(', ')} stored)</span>
              )}
            </dd>
            <dt>Published</dt>
            <dd>
              {paper.published}
              {paper.updated && paper.updated !== paper.published && ` · updated ${paper.updated}`}
            </dd>
            {paper.categories?.length ? (
              <>
                <dt>Categories</dt>
                <dd>
                  {paper.categories.map((c) => (
                    <span key={c} className="pill">
                      {c}
                    </span>
                  ))}
                </dd>
              </>
            ) : null}
            {cleanDoi(paper.doi) && (
              <>
                <dt>DOI</dt>
                <dd className="mono">{cleanDoi(paper.doi)}</dd>
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

          {(paper.summary ?? versions?.versions[0]?.summary) && (
            <p className="abstract">
              <MathText>{paper.summary ?? versions?.versions[0]?.summary}</MathText>
            </p>
          )}
        </>
      )}

      <h3>Tags</h3>
      <div className="tags">
        {paper.tags.map((t) => (
          <span key={t} className="pill">
            {t}
            <button
              className="pill-x"
              title={`Remove ${t}`}
              disabled={!!busy}
              onClick={() => act('tags', () => api.removeTag(id, t))}
            >
              ×
            </button>
          </span>
        ))}
        <form onSubmit={addTag} className="inline">
          <input placeholder="add tags, comma separated" value={newTag} onChange={(e) => setNewTag(e.target.value)} />
          <button disabled={!!busy || !newTag.trim()}>Add</button>
        </form>
        {aiOn && (
          <button type="button" disabled={!!busy} onClick={suggestTags}>
            {busy === 'suggest' ? 'Suggesting…' : 'AI Tags'}
          </button>
        )}
      </div>
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

      <h3>Projects</h3>
      <AddToProjectBar inline selected={paperSelection} onSelect={() => {}} />

      {aiOn && (
        <AiSummary
          key={sid}
          sourceId={sid}
          hasPdf={paper.has_pdf}
          projectId={fromProjectId}
          onSaved={() => setNotesTick((n) => n + 1)}
        />
      )}
      <Notes key={`${sid}:${notesTick}`} sourceId={sid} defaultProjectId={fromProjectId} paper={paper} />

      <h3>PDF</h3>
      {paper.pdf_file && (
        <p className="muted small">
          File: <span className="mono">{paper.pdf_file}</span>
        </p>
      )}
      <div className="actions">
        {paper.has_pdf ? (
          <>
            <button onClick={() => setShowPdf((s) => !s)}>{showPdf ? 'Hide PDF' : 'View PDF'}</button>
            <a href={pdfUrl(sid)} target="_blank" rel="noreferrer">
              Open in new tab
            </a>
            <UndoDeleteButton label="Delete PDF" busy={!!busy} onConfirm={() => act('pdf', () => api.deletePdf(id))} />
          </>
        ) : (
          <>
            <button disabled={!!busy} onClick={() => act('pdf', () => api.downloadPdf(id, customUrl.trim() || undefined))}>
              {busy === 'pdf' ? 'Downloading…' : 'Download PDF'}
            </button>
            <input
              className="grow"
              placeholder="optional PDF URL (needed for non-arXiv papers)"
              value={customUrl}
              onChange={(e) => setCustomUrl(e.target.value)}
            />
          </>
        )}
      </div>
      {(paper.has_pdf || annotations.length > 0) && (
        <Highlights annotations={annotations} sourceId={sid} version={paper.version} onChanged={loadAnnotations} />
      )}

      {(sid.startsWith('arxiv:') || paper.has_pdf) && (
        <>
          <h3>Full text</h3>
          <div className="actions">
            <span className="muted small">
              {paper.downloaded_source
                ? 'Full text indexed: Full text search in the Library covers this paper.'
                : 'Not indexed: Full text search can’t find words inside this paper yet.'}
            </span>
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
            {sourceNote && <span className="small">{sourceNote}</span>}
          </div>
        </>
      )}

      <ErrorText error={error} />

      <h3>Danger zone</h3>
      <div className="actions">
        <UndoDeleteButton label="Delete paper" busy={!!busy} onConfirm={deletePaper} />
        <span className="muted small">Moves the paper to the trash.</span>
      </div>
      </div>

      {split && (
        <>
          <div className="paper-split-handle" onPointerDown={startDrag} role="presentation" title="Drag to resize" />
          <div className="paper-pdf-pane">
            <Suspense fallback={<p className="muted">Loading viewer…</p>}>
              <PdfReader
                key={sid}
                file={pdfUrl(sid)}
                errorUrl={pdfUrl(sid)}
                sourceId={sid}
                version={paper.version}
                projectId={fromProjectId}
                annotations={annotations}
                onAnnotationsChanged={loadAnnotations}
              />
            </Suspense>
          </div>
        </>
      )}
    </section>
  )
}
