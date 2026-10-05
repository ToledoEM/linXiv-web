import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { api, pdfUrl } from '../api'
import type { Paper, PaperVersions } from '../types'
import { Authors, ErrorText } from '../components'

export default function PaperDetail() {
  const id = useParams()['*'] ?? ''
  const navigate = useNavigate()
  const [paper, setPaper] = useState<Paper | null>(null)
  const [versions, setVersions] = useState<PaperVersions | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState('')
  const [newTag, setNewTag] = useState('')
  const [customUrl, setCustomUrl] = useState('')
  const [showPdf, setShowPdf] = useState(false)
  const [confirmDelete, setConfirmDelete] = useState(false)

  const load = useCallback(async () => {
    try {
      setPaper(await api.paper(id))
      setVersions(await api.versions(id).catch(() => null))
      setError('')
    } catch (err) {
      setError((err as Error).message)
    }
  }, [id])

  useEffect(() => {
    load()
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
    if (tags.length) act('tags', () => api.addTags(id, tags)).then(() => setNewTag(''))
  }

  const deletePaper = async () => {
    setBusy('delete')
    try {
      await api.deletePaper(id)
      navigate('/library')
    } catch (err) {
      setError((err as Error).message)
      setBusy('')
    }
  }

  if (!paper) return error ? <ErrorText error={error} /> : <p className="muted">Loading…</p>
  const sid = paper.source_id

  return (
    <section className="detail">
      <h2>{paper.title}</h2>
      <Authors authors={paper.authors} max={50} />
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
        {paper.doi && (
          <>
            <dt>DOI</dt>
            <dd className="mono">{paper.doi}</dd>
          </>
        )}
        {paper.journal_ref && (
          <>
            <dt>Journal</dt>
            <dd>{paper.journal_ref}</dd>
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
        <p className="abstract">{paper.summary ?? versions?.versions[0]?.summary}</p>
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
      </div>

      <h3>PDF</h3>
      <div className="actions">
        {paper.has_pdf ? (
          <>
            <button onClick={() => setShowPdf((s) => !s)}>{showPdf ? 'Hide PDF' : 'View PDF'}</button>
            <a href={pdfUrl(sid)} target="_blank" rel="noreferrer">
              Open in new tab
            </a>
            <button className="danger" disabled={!!busy} onClick={() => act('pdf', () => api.deletePdf(id))}>
              Delete PDF
            </button>
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
      {showPdf && paper.has_pdf && <iframe className="pdf" src={pdfUrl(sid)} title={paper.title} />}

      <ErrorText error={error} />

      <h3>Danger zone</h3>
      <div className="actions">
        {confirmDelete ? (
          <>
            <span>Move this paper to trash?</span>
            <button className="danger" disabled={!!busy} onClick={deletePaper}>
              Yes, delete
            </button>
            <button onClick={() => setConfirmDelete(false)}>Cancel</button>
          </>
        ) : (
          <button className="danger" onClick={() => setConfirmDelete(true)}>
            Delete paper
          </button>
        )}
      </div>
    </section>
  )
}
