import { useEffect, useState } from 'react'
import { api } from './api'
import { ErrorText } from './components'
import type { Job, PdfLayout as Layout, PdfLayoutPreview } from './types'

const LAYOUTS: { value: Layout; label: string }[] = [
  { value: 'none', label: 'No subfolders (flat)' },
  { value: 'year', label: 'Year' },
  { value: 'journal', label: 'Journal' },
  { value: 'year/journal', label: 'Year / Journal' },
  { value: 'journal/year', label: 'Journal / Year' },
]
const POLL_MS = 1000

/** Settings → PDF folders: file saved PDFs into year/journal subfolders on the server. */
export default function PdfLayout() {
  const [current, setCurrent] = useState<Layout>('none')
  const [layout, setLayout] = useState<Layout>('year/journal')
  const [preview, setPreview] = useState<PdfLayoutPreview | null>(null)
  const [job, setJob] = useState<Job | null>(null)
  const [armed, setArmed] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    api
      .settings()
      .then((r) => setCurrent(r.settings.web_pdf_folder_layout))
      .catch(() => {})
    api
      .jobs('pdf-layout')
      .then((jobs) => setJob(jobs[0] ?? null))
      .catch(() => {})
  }, [])

  const running = job?.state === 'running'
  const jobId = job?.id
  useEffect(() => {
    if (!running || jobId === undefined) return
    const t = setInterval(() => {
      api
        .job(jobId)
        .then((j) => {
          setJob(j)
          if (j.state !== 'running') {
            setPreview(null)
            api.settings().then((r) => setCurrent(r.settings.web_pdf_folder_layout)).catch(() => {})
          }
        })
        .catch((err) => setError((err as Error).message))
    }, POLL_MS)
    return () => clearInterval(t)
  }, [running, jobId])

  const runPreview = async (l: Layout) => {
    setBusy(true)
    setError('')
    setArmed(false)
    try {
      setPreview(await api.pdfLayoutPreview(l))
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setBusy(false)
    }
  }

  const apply = async () => {
    if (!armed) return setArmed(true)
    setArmed(false)
    setError('')
    try {
      setJob(await api.startPdfLayout(layout))
    } catch (err) {
      setError((err as Error).message)
    }
  }

  const pct = job && job.total ? Math.round((100 * job.done) / job.total) : 0
  const label = (l: Layout) => LAYOUTS.find((x) => x.value === l)?.label ?? l

  return (
    <div className="card settings-section">
      <h3>PDF folders</h3>
      <p className="muted small">
        Moves the saved PDFs on the server into subfolders and updates linXiv&apos;s record of where each file is.
        Currently: <strong>{label(current)}</strong>. New downloads and imports land in the main folder; apply the layout
        again to file them.
      </p>
      <div className="actions">
        <select
          aria-label="Folder layout"
          value={layout}
          disabled={running}
          onChange={(e) => {
            setLayout(e.target.value as Layout)
            setPreview(null)
            setArmed(false)
          }}
        >
          {LAYOUTS.map((l) => (
            <option key={l.value} value={l.value}>
              {l.label}
            </option>
          ))}
        </select>
        <button type="button" className="link" disabled={busy || running} onClick={() => runPreview(layout)}>
          {busy ? 'Checking…' : 'Preview'}
        </button>
      </div>
      {preview && (
        <div className="layout-preview">
          <p className="small">
            {preview.to_move} to move · {preview.in_place} already in place
            {preview.missing > 0 && ` · ${preview.missing} with no file on disk`}
            {preview.conflicts.length > 0 && ` · ${preview.conflicts.length} conflicts (skipped)`}
          </p>
          {preview.sample.length > 0 && (
            <ul className="plain small mono layout-sample">
              {preview.sample.map((m) => (
                <li key={`${m.source_id}-${m.version}`}>
                  {m.from} → {m.to}
                </li>
              ))}
              {preview.to_move > preview.sample.length && (
                <li className="muted">…and {preview.to_move - preview.sample.length} more</li>
              )}
            </ul>
          )}
          {preview.conflicts.length > 0 && (
            <details className="small">
              <summary>Conflicts</summary>
              <ul className="plain">
                {preview.conflicts.map((c) => (
                  <li key={c}>{c}</li>
                ))}
              </ul>
            </details>
          )}
          <div className="actions">
            <button
              type="button"
              className={armed ? 'danger armed' : ''}
              disabled={running || preview.to_move === 0}
              onBlur={() => setArmed(false)}
              onClick={apply}
            >
              {armed ? `Move ${preview.to_move} PDFs now` : 'Apply'}
            </button>
          </div>
        </div>
      )}
      <ErrorText error={error} />
      {job && (
        <div className="job">
          {running ? (
            <>
              <div className="progress" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100}>
                <span style={{ width: `${pct}%` }} />
              </div>
              <p className="muted small">
                {job.done} of {job.total} {job.current && <span className="mono">· {job.current}</span>}
              </p>
            </>
          ) : (
            <p className="small">
              Last run ({label(((job.result as Record<string, unknown>).layout as Layout) ?? 'none')}) {job.state}: {job.result.moved ?? 0} moved,{' '}
              {job.result.failed ?? 0} failed, {job.result.conflicts ?? 0} conflicts.
            </p>
          )}
          <ErrorText error={job.error ?? undefined} />
          {job.errors.length > 0 && (
            <details className="small">
              <summary>
                {job.errors.length} problem{job.errors.length === 1 ? '' : 's'}
              </summary>
              <ul className="plain">
                {job.errors.map((e, i) => (
                  <li key={i}>
                    <span className="mono">{e.source_id}</span>: {e.error}
                  </li>
                ))}
              </ul>
            </details>
          )}
        </div>
      )}
    </div>
  )
}
